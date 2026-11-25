"""InPost Italy, from the public ShipX tracking resource (no key needed).

Confirmed on real responses: an unknown number answers HTTP 404 with `{"trackingNumber", "message"}` (fixture
`inpost_not_found.json`, 2026-11-22), and a known Italian shipment answers the shape of the ShipX documentation
("Shipment Tracking"): `status`, `tracking_details` newest first with `status`, `origin_status`, `agency`, `location`
(null so far) and an ISO `datetime` with offset, plus `created_at`/`updated_at` (fixture `inpost_in_transit.json`,
2026-11-25, a parcel left at an InPost point). InPost numbers are 24 digits. The later statuses (pickup, delivery)
still come from the documentation (fixture `inpost_documented.json`).
"""
from datetime import UTC, datetime
from typing import Any

from parceldesk.carriers._common import newest_first
from parceldesk.domain import Status, TrackingEvent, TrackingSnapshot
from parceldesk.http import CarrierHttp
from parceldesk.provider import PermanentTrackingError

URL = "https://api-shipx-it.easypack24.net/v1/tracking/{number}"

# ShipX status codes → canonical status and an Italian description (ShipX gives no text)
STATUSES: dict[str, tuple[Status, str]] = {
    "created": ("info_received", "Spedizione creata"),
    "offers_prepared": ("info_received", "Spedizione creata"),
    "offer_selected": ("info_received", "Spedizione creata"),
    "confirmed": ("info_received", "Spedizione confermata dal mittente"),
    "dispatched_by_sender": ("in_transit", "Consegnata dal mittente a InPost"),
    "dispatched_by_sender_to_pok": ("in_transit", "Consegnata dal mittente al punto InPost"),
    "collected_from_sender": ("in_transit", "Ritirata dal mittente"),
    "taken_by_courier": ("in_transit", "Presa in carico dal corriere"),
    "taken_by_courier_from_pok": ("in_transit", "Presa in carico dal corriere"),
    "adopted_at_source_branch": ("in_transit", "Arrivata alla filiale di partenza"),
    "sent_from_source_branch": ("in_transit", "Partita dalla filiale"),
    "adopted_at_sorting_center": ("in_transit", "Arrivata al centro di smistamento"),
    "sent_from_sorting_center": ("in_transit", "Partita dal centro di smistamento"),
    "adopted_at_target_branch": ("in_transit", "Arrivata alla filiale di destinazione"),
    "out_for_delivery": ("out_for_delivery", "In consegna"),
    "out_for_delivery_to_address": ("out_for_delivery", "In consegna all'indirizzo"),
    "ready_to_pickup": ("available_for_pickup", "Pronta per il ritiro nel locker"),
    "ready_to_pickup_from_pok": ("available_for_pickup", "Pronta per il ritiro nel punto InPost"),
    "ready_to_pickup_from_branch": ("available_for_pickup", "Pronta per il ritiro in filiale"),
    "pickup_reminder_sent": ("available_for_pickup", "Promemoria di ritiro inviato"),
    "stack_in_box_machine": ("available_for_pickup", "In attesa in un locker temporaneo"),
    "delivered": ("delivered", "Consegnata"),
    "pickup_time_expired": ("delivery_failure", "Tempo di ritiro scaduto"),
    "avizo": ("delivery_failure", "Destinatario assente, avviso lasciato"),
    "undelivered": ("delivery_failure", "Non consegnata"),
    "rejected_by_receiver": ("exception", "Rifiutata dal destinatario"),
    "returned_to_sender": ("exception", "Restituita al mittente"),
    "claimed": ("exception", "Reclamo aperto"),
    "canceled": ("exception", "Spedizione annullata"),
    "redirect_to_box": ("in_transit", "Reindirizzata a un altro locker"),
    "readdressed": ("in_transit", "Indirizzo di consegna cambiato"),
}


class InPost:
    carrier = "inpost"
    max_batch = 1  # one number per request

    def __init__(self, http: CarrierHttp | None = None):
        self._http = http or CarrierHttp(self.carrier)

    def track(self, numbers: list[str]) -> list[TrackingSnapshot]:
        return [self._one(number) for number in numbers]

    def _one(self, number: str) -> TrackingSnapshot:
        response = self._http.request("GET", URL.format(number=number), expected=(200, 404), headers={"Accept": "application/json"})
        try:
            payload = response.json()
        except ValueError as exc:
            raise PermanentTrackingError("inpost: the tracking resource did not answer JSON") from exc
        if not isinstance(payload, dict):
            raise PermanentTrackingError("inpost: unexpected response shape")
        if response.status_code == 404:
            return TrackingSnapshot(number, "inpost", "not_found", None, [], raw_payload=payload)
        return parse_tracking(number, payload)


def parse_tracking(number: str, payload: dict[str, Any]) -> TrackingSnapshot:
    details = payload.get("tracking_details")
    if not isinstance(details, list):
        raise PermanentTrackingError("inpost: tracking_details missing")
    events = newest_first([_event(d) for d in details if isinstance(d, dict) and d.get("status")])
    code = payload.get("status") or (details[0].get("status") if details and isinstance(details[0], dict) else None)
    status = STATUSES.get(code, ("unknown", ""))[0] if code else ("not_found" if not events else events[0].status)
    delivered = next((e.time_utc for e in events if e.status == "delivered"), None) if status == "delivered" else None
    return TrackingSnapshot(
        number=number, carrier="inpost", status=status, status_raw=code, events=events, delivered_at=delivered, raw_payload=payload,
    )


def _event(detail: dict[str, Any]) -> TrackingEvent:
    code = str(detail["status"])
    status, description = STATUSES.get(code, ("unknown", code.replace("_", " ")))
    local = detail.get("datetime") if isinstance(detail.get("datetime"), str) else None
    return TrackingEvent(
        description=description, time_utc=_time(local), time_local=local,
        location=_location(detail.get("location")) or detail.get("agency") or None, status=status,
    )


def _location(value: Any) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        return value.get("name") or value.get("city") or None
    return None


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None
