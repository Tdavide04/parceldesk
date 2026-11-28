"""Mondial Relay, from the HTML page www.mondialrelay.com/en-gb/parcel-tracking/. One number per request.

Confirmed on real responses (fixtures `mondialrelay_in_transit.html` and `mondialrelay_not_found.html`, 2026-11-28):
a parcel is found by its 8-digit shipment number (`exp`) together with the sender's brand code (`ens`); without
the brand code, or with an unknown number, the page shows its search form and no event blocks. Each day is an
`infos-account` block with an MM/DD/YYYY date and steps of a 12-hour time and a sentence, newest first.

The brand code defaults to Vinted's (`V1TTO`): InPost hands Vinted's international parcels to Mondial Relay, and
their labels carry the 8-digit number only. Parcels of other senders need their own brand code.
Times are taken as Central European time (the sites are in Italy, France and Germany alike).
Confirmed phrases: "Parcel in preparation at the sender", "Parcel picked up in the Pudo", "Parcel taken over by
agency ...", "Parcel shipped from the site ...". The pickup and delivery phrases are assumed from the page's
progress bar ("Parcel available at the Point Relais", "Delivered parcel") until a real one is seen.
"""
import html
import re
from datetime import UTC, datetime

from parceldesk.carriers._common import ROME, newest_first
from parceldesk.domain import Status, TrackingEvent, TrackingSnapshot
from parceldesk.http import CarrierHttp
from parceldesk.provider import PermanentTrackingError

URL = "https://www.mondialrelay.com/en-gb/parcel-tracking/"
VINTED = "V1TTO"
DAY = re.compile(r'<div class="infos-account">.*?<p>(\d{2}/\d{2}/\d{4})</p>(.*?)(?=<div class="infos-account">|</body>|\Z)', re.S)
STEP = re.compile(r'<p class="center">\s*(\d{1,2}:\d{2}\s*[AP]M)\s*</p>\s*</div>\s*<div class="col-xs-8[^"]*">\s*<p>([^<]+)</p>', re.S)
PHRASES: tuple[tuple[str, Status], ...] = (
    (r"delivered parcel|delivered to the recipient|(collected|picked up) by the recipient|livré au destinataire", "delivered"),
    (r"available at the point relais|available for collection|disponible", "available_for_pickup"),
    (r"in preparation at the sender", "info_received"),
    (r"picked up|taken over|shipped|expédié|in transit|pris en charge", "in_transit"),
)


def status_of(phrase: str) -> Status:
    text = phrase.lower()
    return next((status for pattern, status in PHRASES if re.search(pattern, text)), "unknown")


class MondialRelay:
    carrier = "mondialrelay"
    max_batch = 1

    def __init__(self, http: CarrierHttp | None = None, brand: str = VINTED):
        self._http = http or CarrierHttp(self.carrier)
        self._brand = brand

    def track(self, numbers: list[str]) -> list[TrackingSnapshot]:
        return [self._one(number) for number in numbers]

    def _one(self, number: str) -> TrackingSnapshot:
        response = self._http.request("GET", URL, params={"ens": self._brand, "exp": number, "language": "EN"})
        return parse_page(number, response.text)


def parse_page(number: str, page: str) -> TrackingSnapshot:
    days = DAY.findall(page)
    if not days:
        if "Parcel Tracking" not in page:
            raise PermanentTrackingError("mondialrelay: neither events nor the tracking page: the page has changed")
        return TrackingSnapshot(number, "mondialrelay", "not_found", None, [], raw_payload=page)
    events = newest_first([_event(day, time, text) for day, block in days for time, text in STEP.findall(block)])
    if not events:
        raise PermanentTrackingError("mondialrelay: days without steps: the page has changed")
    return TrackingSnapshot(
        number=number, carrier="mondialrelay", status=events[0].status, status_raw=events[0].description, events=events,
        delivered_at=events[0].time_utc if events[0].status == "delivered" else None, raw_payload=page,
    )


def _event(day: str, time: str, text: str) -> TrackingEvent:
    local = datetime.strptime(f"{day} {time.replace(' ', '')}", "%m/%d/%Y %I:%M%p").replace(tzinfo=ROME)
    description = html.unescape(text).strip()
    return TrackingEvent(description, local.astimezone(UTC), local.isoformat(), None, status_of(description))
