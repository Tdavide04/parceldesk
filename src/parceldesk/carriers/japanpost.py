"""Japan Post, from the HTML page trackings.post.japanpost.jp/services/srv/search/direct (locale=en). One number per request.

Confirmed on real responses (fixtures `japanpost_in_transit.html` and `japanpost_not_found.html`, 2026-11-28): the
"History information" table has one event per pair of rows, whose first row holds date and time (MM/DD/YYYY HH:MM),
the event, details, the office and the prefecture or country; an unknown number says "Your item was not found".
Times are local: Japan time in Japan, the country's own time abroad ("In local time if occurred overseas").
Confirmed events: "Posting/Collection", "Arrival at outward office of exchange", "Dispatch from outward office of
exchange". The others follow the international postal (UPU) event names until a real one is seen.

International items (`LX123456789JP`) are tracked by Poste Italiane too once in Italy; the hub joins both.
"""
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from parceldesk.carriers._common import newest_first, page_text, table_rows
from parceldesk.domain import Status, TrackingEvent, TrackingSnapshot
from parceldesk.http import CarrierHttp
from parceldesk.provider import PermanentTrackingError

URL = "https://trackings.post.japanpost.jp/services/srv/search/direct"
NOT_FOUND = re.compile(r"Your item was not found")
WHEN = re.compile(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}")
TOKYO = ZoneInfo("Asia/Tokyo")
# shortcut: only Italy is told apart abroad (it is where these parcels go); add a country here when another shows up
COUNTRY_ZONES = {"ITALY": ZoneInfo("Europe/Rome")}
PHRASES: tuple[tuple[str, Status], ...] = (
    (r"final delivery|delivered", "delivered"),
    (r"absence|unsuccessful|attempted delivery", "delivery_failure"),
    (r"return|refus|damage|lost", "exception"),
    (r"out for delivery|in delivery", "out_for_delivery"),
    (r"awaiting collection|held at (the )?(post )?office|retention", "available_for_pickup"),
    (r"posting|acceptance|arrival|dispatch|customs|transit|inward|outward", "in_transit"),
)


def status_of(phrase: str) -> Status:
    text = phrase.lower()
    return next((status for pattern, status in PHRASES if re.search(pattern, text)), "unknown")


class JapanPost:
    carrier = "japanpost"
    max_batch = 1

    def __init__(self, http: CarrierHttp | None = None):
        self._http = http or CarrierHttp(self.carrier)

    def track(self, numbers: list[str]) -> list[TrackingSnapshot]:
        return [self._one(number) for number in numbers]

    def _one(self, number: str) -> TrackingSnapshot:
        response = self._http.request("GET", URL, params={"reqCodeNo1": number, "searchKind": "S002", "locale": "en"})
        return parse_page(number, response.text)


def parse_page(number: str, page: str) -> TrackingSnapshot:
    if NOT_FOUND.search(page_text(page)):
        return TrackingSnapshot(number, "japanpost", "not_found", None, [], raw_payload=page)
    events = newest_first([_event(cells) for cells in table_rows(page) if len(cells) >= 5 and WHEN.fullmatch(cells[0])])
    if not events:
        raise PermanentTrackingError("japanpost: no history rows and no not-found message: the page has changed")
    return TrackingSnapshot(
        number=number, carrier="japanpost", status=events[0].status, status_raw=events[0].description, events=events,
        delivered_at=events[0].time_utc if events[0].status == "delivered" else None, raw_payload=page,
    )


def _event(cells: list[str]) -> TrackingEvent:
    when, record, details, office, region = cells[:5]
    zone = COUNTRY_ZONES.get(region.upper(), TOKYO)
    local = datetime.strptime(when, "%m/%d/%Y %H:%M").replace(tzinfo=zone)
    description = f"{record} ({details})" if details else record
    location = ", ".join(part for part in (office, region) if part) or None
    return TrackingEvent(description, local.astimezone(UTC), local.isoformat(), location, status_of(record))
