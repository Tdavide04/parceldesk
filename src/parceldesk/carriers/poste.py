"""Poste Italiane, from the JSON endpoint behind www.poste.it/cerca (the "Dove e quando" search).

One POST answers several numbers. Confirmed on real responses (fixtures `poste_*.json`, 2026-11-22):
- every number asked comes back once, keyed by `idTracciatura`;
- an unknown number has `esitoRicerca` "2" and an empty `listaMovimenti`;
- movements come oldest first, `dataOra` is epoch milliseconds, `statoLavorazione` is the carrier's sentence;
- `dataPrevistaConsegna` is a sentence ("Consegna prevista entro lunedì 30 novembre 2026").

Statuses come from the sentence, with the phrases shared by all carriers (`carriers._common.PHRASES`).
"""
from datetime import UTC, datetime
from typing import Any

from parceldesk.carriers._common import ROME, status_of
from parceldesk.domain import Status, TrackingEvent, TrackingSnapshot
from parceldesk.http import CarrierHttp
from parceldesk.provider import PermanentTrackingError

URL = "https://www.poste.it/online/dovequando/DQ-REST/ricercamultipla"


class PosteItaliane:
    carrier = "poste"
    max_batch = 10

    def __init__(self, http: CarrierHttp | None = None):
        self._http = http or CarrierHttp(self.carrier)

    def track(self, numbers: list[str]) -> list[TrackingSnapshot]:
        response = self._http.request(
            "POST", URL, json={"tipoRichiedente": "WEB", "listaCodici": list(numbers)},
            headers={"Content-Type": "application/json", "Origin": "https://www.poste.it", "Referer": "https://www.poste.it/cerca/index.html"},
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise PermanentTrackingError("poste: the tracking endpoint did not answer JSON") from exc
        if not isinstance(payload, list):
            raise PermanentTrackingError("poste: unexpected response shape")
        return [parse_shipment(item) for item in payload if isinstance(item, dict) and item.get("idTracciatura")]


def parse_shipment(item: dict[str, Any]) -> TrackingSnapshot:
    movements = item.get("listaMovimenti") or []
    events = [event for event in (_event(m) for m in reversed(movements) if isinstance(m, dict)) if event is not None]
    if not events:
        status: Status = "not_found"
        status_raw = None
    else:
        status = events[0].status
        status_raw = events[0].description
    delivered_at = events[0].time_utc if events and status == "delivered" else None
    return TrackingSnapshot(
        number=str(item["idTracciatura"]).upper(),
        carrier="poste",
        status=status,
        status_raw=status_raw,
        events=events,
        delivered_at=delivered_at,
        estimated_delivery=item.get("dataPrevistaConsegna") or None,
        raw_payload=item,
    )


def _event(movement: dict[str, Any]) -> TrackingEvent | None:
    description = (movement.get("statoLavorazione") or "").strip()
    if not description:
        return None
    time_utc = _time(movement.get("dataOra"))
    return TrackingEvent(
        description=description,
        time_utc=time_utc,
        time_local=time_utc.astimezone(ROME).isoformat() if time_utc else None,
        location=(movement.get("luogo") or "").strip() or None,
        status=status_of(description),
    )


def _time(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
