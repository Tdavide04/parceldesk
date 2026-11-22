"""HTTP for carrier sites: one request at a time per carrier, a minimum gap between requests, retries with backoff.

Carriers publish no limits for their tracking pages, so the default gap is generous. 429, 5xx, timeouts and
connection errors are retried, honouring Retry-After; any other status the caller did not list as expected means
access was refused or the endpoint moved, which a retry will not fix.
"""
import logging
import time
from collections.abc import Callable, Collection
from typing import Any

import requests

from parceldesk.provider import PermanentTrackingError, TransientTrackingError

logger = logging.getLogger(__name__)

USER_AGENT = "parceldesk/0.2 (+https://github.com/Tdavide04/parceldesk)"
MAX_RETRY_AFTER_S = 120.0


class CarrierHttp:
    def __init__(
        self,
        carrier: str,
        session: Any | None = None,
        min_interval_s: float = 2.0,
        timeout_s: float = 30.0,
        max_retries: int = 3,
        backoff_s: float = 2.0,
        user_agent: str = USER_AGENT,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.carrier = carrier
        self._session = session if session is not None else requests.Session()
        self._min_interval = min_interval_s
        self._timeout = timeout_s
        self._max_retries = max_retries
        self._backoff = backoff_s
        self._user_agent = user_agent
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def request(self, method: str, url: str, expected: Collection[int] = (200,), **kwargs: Any) -> requests.Response:
        headers = {"User-Agent": self._user_agent, **(kwargs.pop("headers", None) or {})}
        wait = 0.0
        reason = ""
        for attempt in range(self._max_retries + 1):
            self._wait(wait)
            try:
                response = self._session.request(method, url, headers=headers, timeout=self._timeout, **kwargs)
            except (requests.Timeout, requests.ConnectionError) as exc:
                reason = type(exc).__name__
                wait = self._backoff * 2**attempt
            else:
                status = response.status_code
                if status in expected:
                    return response
                if status != 429 and status < 500:
                    raise PermanentTrackingError(f"{self.carrier}: HTTP {status} from {url}")
                reason = f"HTTP {status}"
                wait = _retry_after(response) or self._backoff * 2**attempt
            logger.warning(
                "tracking request retried",
                extra={"event": "tracking_retry", "carrier": self.carrier, "attempt": attempt + 1, "reason": reason},
            )
        raise TransientTrackingError(f"{self.carrier}: {url} failed after {self._max_retries + 1} attempts ({reason})")

    def _wait(self, backoff: float) -> None:
        left = 0.0 if self._last is None else self._min_interval - (self._clock() - self._last)
        wait = max(backoff, left)
        if wait > 0:
            self._sleep(wait)
        self._last = self._clock()


def _retry_after(response: Any) -> float | None:
    value = response.headers.get("Retry-After")
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_S)
