"""Mondial Relay (InPost group), from the public tracking page www.mondialrelay.com/it-it/parcel-tracking/.

Vinted hands out an 8-digit Mondial Relay "expedition" number for parcels it labels InPost but sends abroad, with a
link such as `parcel-tracking/?country=DE&ens=V1ITTODE&exp=<number>&language=EN`. A GET of that link answers the
tracking rendered on the server, with no postcode and no bot check (seen 2026-11-25); the form on the same page
(`SuiviExpedition/RechercherJsonResponsive`) asks for the recipient's postcode instead, so it is not used.

Confirmed on real responses: a known parcel (fixture `mondialrelay_in_transit.html`, 2026-11-25, Italian page,
anonymised) shows a five-step progress bar (`ul.timeline.suivi`, reached steps carry `class="validate"`), then one
`div.infos-account` per day, newest first, with the date (DD/MM/YYYY on the Italian page) and `div.step-suivi`
events, newest first, each a time (`p.center`, 24h) and a sentence. Some sentences come in French whatever the page
language, and the newest event may repeat its sentence in a second block without a time. An unknown number shows
"Oups, vous êtes actuellement très nombreux..." with a request to check the number (fixture
`mondialrelay_not_found.html`), which the provider reads as not found.

`ens` (the sender's brand code, `V1ITTODE` for Vinted Italy to Germany) and `country` (the destination) come from the
link; they are optional settings of the provider because it is not yet known whether the page needs them.
"""
import html as html_lib
import re

from parceldesk.carriers._common import local_time, newest_first, page_text, status_of
from parceldesk.domain import Status, TrackingEvent, TrackingSnapshot
from parceldesk.http import CarrierHttp
from parceldesk.provider import PermanentTrackingError

URL = "https://www.mondialrelay.com/it-it/parcel-tracking/"
NOT_FOUND = re.compile(r"Oups, vous êtes actuellement|numéro de colis saisi soit le bon")

# the five steps of the progress bar, by position: the last reached one is the parcel's status
STEPS: tuple[Status, ...] = ("info_received", "in_transit", "in_transit", "available_for_pickup", "delivered")

# Mondial Relay sentences, Italian and French, lower-cased; checked before the shared phrases because
# "consegnato a Mondial Relay" is not a delivery
PHRASES: tuple[tuple[str, Status], ...] = (
    (r"in preparazione|en préparation|en preparation", "info_received"),
    (r"consegnato a mondial relay|preso in carico|pris en charge|remis à mondial relay|expédié|exp.di.", "in_transit"),
    (r"disponibile|disponible|al point relais|au point relais", "available_for_pickup"),
    (r"\bconsegnato\b(?! a mondial)|livré", "delivered"),
)

TIMELINE = re.compile(r'<ul class="timeline suivi[^"]*">(.*?)</ul>', re.S)
STEP = re.compile(r"<li\s*(class=\"validate\")?\s*>\s*<p>(.*?)</p>", re.S)
DAY = re.compile(r'<div class="infos-account">')
DATE = re.compile(r"<p>\s*(\d{1,2}/\d{1,2}/\d{4})\s*</p>")
EVENT = re.compile(
    r'<p class="center">\s*([0-9]{1,2}[:.][0-9]{2})\s*</p>\s*</div>\s*<div class="col-xs-8[^"]*">\s*<p>(.*?)</p>', re.S
)


def mondialrelay_status(sentence: str) -> Status:
    text = sentence.lower()
    for pattern, status in PHRASES:
        if re.search(pattern, text):
            return status
    return status_of(sentence)


class MondialRelay:
    carrier = "mondialrelay"
    max_batch = 1

    def __init__(self, http: CarrierHttp | None = None, ens: str | None = None, country: str | None = None):
        self._http = http or CarrierHttp(self.carrier)
        self._ens = ens
        self._country = country

    def track(self, numbers: list[str]) -> list[TrackingSnapshot]:
        return [self._one(number) for number in numbers]

    def _one(self, number: str) -> TrackingSnapshot:
        params = {"exp": number, "language": "IT"}
        if self._ens:
            params["ens"] = self._ens
        if self._country:
            params["country"] = self._country
        response = self._http.request("GET", URL, params=params)
        return parse_page(number, response.text)


def parse_page(number: str, page: str) -> TrackingSnapshot:
    timeline = TIMELINE.search(page)
    if timeline is None:
        if NOT_FOUND.search(page_text(page)):
            return TrackingSnapshot(number, "mondialrelay", "not_found", None, [], raw_payload=page)
        raise PermanentTrackingError("mondialrelay: no progress bar and no not-found message: the page has changed")
    steps = [(bool(reached), _text(label)) for reached, label in STEP.findall(timeline.group(1))]
    reached = [i for i, (done, _) in enumerate(steps) if done]
    events = newest_first([e for chunk in DAY.split(page)[1:] for e in _day_events(chunk)])
    if reached and len(steps) == len(STEPS):
        status, status_raw = STEPS[reached[-1]], steps[reached[-1]][1]
    elif events:
        status, status_raw = events[0].status, events[0].description
    else:
        status, status_raw = "not_found", None
    delivered = next((e.time_utc for e in events if e.status == "delivered"), None) if status == "delivered" else None
    return TrackingSnapshot(
        number=number, carrier="mondialrelay", status=status, status_raw=status_raw, events=events,
        delivered_at=delivered, raw_payload=page,
    )


def _day_events(chunk: str) -> list[TrackingEvent]:
    date = DATE.search(chunk)
    if date is None:
        return []
    events = []
    for clock, sentence in EVENT.findall(chunk):
        description = _text(sentence)
        if description:
            time_utc, time_local = local_time(date.group(1), clock)
            events.append(TrackingEvent(description, time_utc, time_local, None, mondialrelay_status(description)))
    return events


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()
