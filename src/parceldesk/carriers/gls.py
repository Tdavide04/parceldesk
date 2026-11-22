"""GLS Italy, from the HTML form on www.gls-italy.com ("Ricerca spedizione"). One number per request.

Confirmed on a real response (fixture `gls_not_found.html`, 2026-11-22): an unknown number shows the sentence
"La spedizione potrebbe non essere ancora stata affidata alla Sede GLS ...". The layout of a known shipment is not
confirmed: it follows public scrapers of this page (an "ESITO SPEDIZIONE" table whose rows hold date and time,
place and status). The parser is deliberately loose: it takes every table row with a date in its first cell.
"""
import re
from typing import Any

from parceldesk.carriers._common import local_time, newest_first, page_text, status_of, table_rows
from parceldesk.domain import TrackingEvent, TrackingSnapshot
from parceldesk.http import CarrierHttp
from parceldesk.provider import PermanentTrackingError

URL = "https://www.gls-italy.com/it/servizi-per-destinatari/dettaglio-spedizione"
NOT_FOUND = "potrebbe non essere ancora stata affidata"
NATIONAL = re.compile(r"[A-Z][A-Z0-9]\d{1,9}")
INTERNATIONAL = re.compile(r"\d{11}")


def code_type(number: str) -> str:
    if NATIONAL.fullmatch(number):
        return "nazionale"
    if INTERNATIONAL.fullmatch(number):
        return "internazionale"
    return "id_collo"


class Gls:
    carrier = "gls"
    max_batch = 1

    def __init__(self, http: CarrierHttp | None = None):
        self._http = http or CarrierHttp(self.carrier)

    def track(self, numbers: list[str]) -> list[TrackingSnapshot]:
        return [self._one(number) for number in numbers]

    def _one(self, number: str) -> TrackingSnapshot:
        form: dict[str, Any] = {
            "numero_spedizione": number, "tipo_codice": code_type(number), "option": "com_gls", "view": "track_e_trace",
            "mode": "search", "tabelle_memorizzate": "1", "filtro_codice": "0", "pagina": "1", "reclast": "",
        }
        response = self._http.request("POST", URL, data=form)
        return parse_page(number, response.text)


def parse_page(number: str, html: str) -> TrackingSnapshot:
    text = page_text(html)
    if NOT_FOUND in text:
        return TrackingSnapshot(number, "gls", "not_found", None, [], raw_payload=html)
    events = newest_first([e for e in (_event(row) for row in table_rows(html)) if e is not None])
    if not events:
        raise PermanentTrackingError("gls: no tracking table and no not-found message: the page has changed")
    return TrackingSnapshot(
        number=number, carrier="gls", status=events[0].status, status_raw=events[0].description, events=events,
        delivered_at=events[0].time_utc if events[0].status == "delivered" else None, raw_payload=html,
    )


def _event(cells: list[str]) -> TrackingEvent | None:
    if len(cells) < 3:
        return None
    time_utc, time_local = local_time(cells[0])
    if time_utc is None:
        return None
    description = cells[-1]
    location = cells[1] if len(cells) >= 3 else None
    if not description:
        return None
    return TrackingEvent(description, time_utc, time_local, location or None, status_of(description))
