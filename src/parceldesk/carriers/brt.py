"""BRT, from the HTML page vas.brt.it/vas/sped_det_show.hsm. One number per request.

Confirmed on real responses (fixture `brt_not_found.html`, 2026-11-22): `Nspediz` takes exactly 12 digits
("Immettere un numero spedizione di 12 cifre"), and an unknown one shows error TIS0564 ("Spedizione non trovata
oppure ancora in elaborazione"). Longer parcel codes go in `brtCode`, as public scrapers of this page do (not
confirmed). The layout of a known shipment is not confirmed either: public scrapers read rows of four cells
(date, time, branch, event). The parser takes every table row whose first two cells are a date and a time.
"""
import re

from parceldesk.carriers._common import DATE, TIME, local_time, newest_first, page_text, status_of, table_rows
from parceldesk.domain import TrackingEvent, TrackingSnapshot
from parceldesk.http import CarrierHttp
from parceldesk.provider import PermanentTrackingError

URL = "https://vas.brt.it/vas/sped_det_show.hsm"
NOT_FOUND = re.compile(r"TIS0564|Spedizione non trovata")
SHIPMENT_NUMBER = re.compile(r"\d{12}")


class Brt:
    carrier = "brt"
    max_batch = 1

    def __init__(self, http: CarrierHttp | None = None):
        self._http = http or CarrierHttp(self.carrier)

    def track(self, numbers: list[str]) -> list[TrackingSnapshot]:
        return [self._one(number) for number in numbers]

    def _one(self, number: str) -> TrackingSnapshot:
        key = "Nspediz" if SHIPMENT_NUMBER.fullmatch(number) else "brtCode"
        response = self._http.request("GET", URL, params={"referer": "sped_numspe_par.htm", key: number})
        response.encoding = response.encoding or "iso-8859-15"  # the page declares it, the header may not
        return parse_page(number, response.text)


def parse_page(number: str, html: str) -> TrackingSnapshot:
    if NOT_FOUND.search(page_text(html)):
        return TrackingSnapshot(number, "brt", "not_found", None, [], raw_payload=html)
    events = newest_first([e for e in (_event(row) for row in table_rows(html)) if e is not None])
    if not events:
        raise PermanentTrackingError("brt: no tracking rows and no not-found message: the page has changed or refused the number")
    return TrackingSnapshot(
        number=number, carrier="brt", status=events[0].status, status_raw=events[0].description, events=events,
        delivered_at=events[0].time_utc if events[0].status == "delivered" else None, raw_payload=html,
    )


def _event(cells: list[str]) -> TrackingEvent | None:
    if len(cells) < 4 or not DATE.fullmatch(cells[0]) or not TIME.fullmatch(cells[1]):
        return None
    description = cells[3]
    if not description:
        return None
    time_utc, time_local = local_time(cells[0], cells[1])
    return TrackingEvent(description, time_utc, time_local, cells[2] or None, status_of(description))
