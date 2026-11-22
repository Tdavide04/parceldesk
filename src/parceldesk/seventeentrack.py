"""17TRACK Tracking API v2.4 (https://api.17track.net/en/doc), polling only.

Every endpoint is a POST with a JSON body and the `17token` header. Batch endpoints take at most 40 numbers;
the account limit is 3 requests per second (HTTP 429 beyond). A batch answers HTTP 200 with `code: 0` even when
some numbers fail: those come back in `data.rejected`. Shapes follow the documentation; the open points listed in
the hub's research notes (docs/research/17track-api.md) are handled defensively.
"""
import logging
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import requests

from parceldesk.domain import (
    Accepted,
    BatchResult,
    Quota,
    Registration,
    RejectedNumber,
    Status,
    TrackedNumber,
    TrackingEvent,
    TrackingResult,
    TrackingSnapshot,
)
from parceldesk.provider import PermanentTrackingError, TransientTrackingError

logger = logging.getLogger(__name__)

BASE_URL = "https://api.17track.net/track/v2.4"
BATCH_SIZE = 40
MIN_INTERVAL_S = 0.35  # 3 requests per second, with a margin

STATUSES: dict[str, Status] = {
    "NotFound": "not_found", "InfoReceived": "info_received", "InTransit": "in_transit", "Expired": "expired",
    "AvailableForPickup": "available_for_pickup", "OutForDelivery": "out_for_delivery",
    "DeliveryFailure": "delivery_failure", "Delivered": "delivered", "Exception": "exception",
}
# request-level errors that no retry fixes
PERMANENT_CODES = {
    -18010001: "IP not in the whitelist", -18019907: "daily tracking limit reached", -18019908: "quota exhausted",
}


class SeventeenTrack:
    """TrackingProvider on 17TRACK. Holds no state beyond its HTTP session and the time of the last request."""

    name = "17track"

    def __init__(
        self,
        api_key: str,
        session: Any | None = None,
        base_url: str = BASE_URL,
        timeout_s: float = 30.0,
        max_retries: int = 3,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not api_key:
            raise ValueError("a 17TRACK API key is required")
        self._key = api_key
        self._session = session if session is not None else requests.Session()
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s
        self._max_retries = max_retries
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    # --- TrackingProvider ---------------------------------------------------------------------------

    def register(self, registrations: list[Registration]) -> BatchResult:
        return self._batch("register", [_registration_body(r) for r in registrations])

    def track(self, numbers: list[TrackedNumber]) -> TrackingResult:
        snapshots: list[TrackingSnapshot] = []
        rejected: list[RejectedNumber] = []
        for chunk in _chunks([_number_body(n) for n in numbers]):
            data = self._post("gettrackinfo", chunk)
            for item in data.get("accepted") or []:
                try:
                    snapshots.append(parse_snapshot(item))
                except (KeyError, TypeError, ValueError) as exc:
                    rejected.append(RejectedNumber(str(item.get("number", "")), None, f"unreadable tracking info: {exc}"))
            rejected.extend(_rejected(data))
        return TrackingResult(snapshots, rejected)

    def stop(self, numbers: list[TrackedNumber]) -> BatchResult:
        return self._batch("stoptrack", [_number_body(n) for n in numbers])

    def reactivate(self, numbers: list[TrackedNumber]) -> BatchResult:
        return self._batch("retrack", [_number_body(n) for n in numbers])

    def quota(self) -> Quota:
        data = self._post("getquota", {})
        try:
            return Quota(total=int(data["quota_total"]), used=int(data["quota_used"]), remaining=int(data["quota_remain"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise PermanentTrackingError(f"17track: unexpected quota response ({exc})") from exc

    # --- transport ----------------------------------------------------------------------------------

    def _batch(self, endpoint: str, bodies: list[dict[str, Any]]) -> BatchResult:
        accepted: list[Accepted] = []
        rejected: list[RejectedNumber] = []
        for chunk in _chunks(bodies):
            data = self._post(endpoint, chunk)
            accepted.extend(Accepted(str(a["number"]), _carrier(a.get("carrier"))) for a in data.get("accepted") or [])
            rejected.extend(_rejected(data))
        return BatchResult(accepted, rejected)

    def _post(self, endpoint: str, body: Any) -> dict[str, Any]:
        url = f"{self._base}/{endpoint}"
        for attempt in range(self._max_retries + 1):
            self._wait(0 if attempt == 0 else min(30.0, 2.0 * 2**attempt))
            try:
                response = self._session.request("POST", url, json=body, headers={"17token": self._key, "Content-Type": "application/json"}, timeout=self._timeout)
            except (requests.Timeout, requests.ConnectionError) as exc:
                reason = type(exc).__name__
            else:
                status = response.status_code
                if status == 401:
                    raise PermanentTrackingError("17track: HTTP 401 (invalid key, IP not allowed or account disabled)")
                if status == 429 or status >= 500:
                    reason = f"HTTP {status}"
                elif status >= 400:
                    raise PermanentTrackingError(f"17track: HTTP {status} from {endpoint}")
                else:
                    return self._envelope(endpoint, response)
            logger.warning("tracking request retried", extra={"event": "tracking_retry", "provider": self.name, "endpoint": endpoint, "attempt": attempt + 1, "reason": reason})
        raise TransientTrackingError(f"17track: {endpoint} failed after {self._max_retries + 1} attempts ({reason})")

    def _envelope(self, endpoint: str, response: Any) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise PermanentTrackingError(f"17track: {endpoint} did not answer JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise PermanentTrackingError(f"17track: unexpected response from {endpoint}")
        code = payload.get("code")
        errors = payload["data"].get("errors") or []
        if code != 0 or errors:
            first = errors[0] if errors and isinstance(errors[0], dict) else {}
            error_code = first.get("code", code)
            message = PERMANENT_CODES.get(error_code) or first.get("message") or f"code {code}"
            raise PermanentTrackingError(f"17track: {endpoint}: {message}", code=error_code)
        return payload["data"]

    def _wait(self, backoff: float) -> None:
        left = 0.0 if self._last is None else MIN_INTERVAL_S - (self._clock() - self._last)
        wait = max(backoff, left)
        if wait > 0:
            self._sleep(wait)
        self._last = self._clock()


def _chunks(items: list[Any]) -> Iterator[list[Any]]:
    for start in range(0, len(items), BATCH_SIZE):
        yield items[start:start + BATCH_SIZE]


def _number_body(n: TrackedNumber) -> dict[str, Any]:
    body: dict[str, Any] = {"number": n.number}
    if n.carrier is not None:
        body["carrier"] = n.carrier
    return body


def _registration_body(r: Registration) -> dict[str, Any]:
    body = _number_body(r)
    for name in ("tag", "origin_country", "destination_country", "destination_postal_code", "lang"):
        value = getattr(r, name)
        if value is not None:
            body[name] = value
    return body


def _carrier(value: Any) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _rejected(data: dict[str, Any]) -> list[RejectedNumber]:
    out = []
    for item in data.get("rejected") or []:
        error = item.get("error") or {}
        out.append(RejectedNumber(str(item.get("number", "")), error.get("code"), error.get("message") or "rejected"))
    return out


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _status(value: Any) -> Status:
    return STATUSES.get(value, "unknown") if isinstance(value, str) else "unknown"


def _status_of_sub(sub_status: Any) -> Status:
    return _status(sub_status.split("_", 1)[0]) if isinstance(sub_status, str) else "unknown"


def parse_snapshot(item: dict[str, Any]) -> TrackingSnapshot:
    """One `gettrackinfo` (or webhook) item. Events from every provider, merged newest first."""
    info = item.get("track_info") or {}
    latest = info.get("latest_status") or {}
    tracking = info.get("tracking") or {}
    events: list[TrackingEvent] = []
    hashes = []
    for provider in tracking.get("providers") or []:
        name = (provider.get("provider") or {}).get("name")
        hashes.append(str(provider.get("events_hash") or ""))
        for e in provider.get("events") or []:
            events.append(TrackingEvent(
                description=str(e.get("description") or ""),
                time_utc=_time(e.get("time_utc")) or _time(e.get("time_iso")),
                time_local=e.get("time_iso"),
                location=e.get("location") or None,
                status=_status_of_sub(e.get("sub_status")),
                sub_status=e.get("sub_status"),
                carrier_name=name,
            ))
    events.sort(key=lambda e: e.time_utc or datetime.min.replace(tzinfo=UTC), reverse=True)
    delivered = next((e.time_utc for e in events if e.status == "delivered"), None)
    estimate = (info.get("time_metrics") or {}).get("estimated_delivery_date") or {}
    events_hash = tracking.get("providers_hash")
    if events_hash is None and hashes:
        events_hash = "|".join(hashes)
    return TrackingSnapshot(
        number=str(item["number"]),
        carrier=_carrier(item.get("carrier")),
        status=_status(latest.get("status")),
        status_raw=latest.get("status"),
        sub_status=latest.get("sub_status"),
        sub_status_description=latest.get("sub_status_descr"),
        events=events,
        events_hash=None if events_hash is None else str(events_hash),
        delivered_at=delivered,
        estimated_delivery_from=_time(estimate.get("from")),
        estimated_delivery_to=_time(estimate.get("to")),
        tag=item.get("tag") or None,
        raw_payload=item,
    )
