"""Helpers shared by the carrier providers: Italian status phrases, HTML table rows, local dates."""
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from parceldesk.domain import Status, TrackingEvent

ROME = ZoneInfo("Europe/Rome")

# Regular expressions on the carrier's sentence, lower-cased; the first match wins, so the more specific come
# first. Confirmed on real responses so far: "presa in carico" and "in transito" (Poste). The rest follow the
# wording of the carriers' pages and map to `unknown` when a carrier words things differently.
PHRASES: tuple[tuple[str, Status], ...] = (
    (r"\bnon\b.*consegnat|mancata consegna|tentativo di consegna|destinatario assente", "delivery_failure"),
    (r"in restituzione|reso al mittente|rientrata al mittente|smarrit|danneggiat|respint|rifiutat", "exception"),
    (r"consegnat", "delivered"),
    (r"in consegna|affidata al corriere per la consegna|in distribuzione", "out_for_delivery"),
    (r"disponibile (per il|al) ritiro|pronta per il ritiro|in giacenza|fermopoint|punto di ritiro", "available_for_pickup"),
    (r"in transito|partit|arrivat|in lavorazione|presa in carico|ritirat|smistat|in viaggio", "in_transit"),
    (r"dati ricevuti|in attesa di|registrat|creat", "info_received"),
)


def status_of(phrase: str) -> Status:
    text = phrase.lower()
    for pattern, status in PHRASES:
        if re.search(pattern, text):
            return status
    return "unknown"


DATE = re.compile(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})")
TIME = re.compile(r"(\d{1,2})[.:](\d{2})")


def local_time(date_text: str, time_text: str = "") -> tuple[datetime | None, str | None]:
    """A carrier date (dd.mm.yyyy, dd/mm/yy...) and optional time in Italian local time → (UTC, local ISO)."""
    date = DATE.search(date_text or "")
    if not date:
        return None, None
    day, month, year = (int(g) for g in date.groups())
    year += 2000 if year < 100 else 0
    clock = TIME.search((time_text or "") + " " + (date_text or "")[date.end():])
    hour, minute = (int(clock.group(1)), int(clock.group(2))) if clock else (0, 0)
    try:
        local = datetime(year, month, day, hour, minute, tzinfo=ROME)
    except ValueError:
        return None, None
    return local.astimezone(UTC), local.isoformat()


def newest_first(events: list[TrackingEvent]) -> list[TrackingEvent]:
    """Pages list scans in either order; sort by time, keeping the page order for scans without one."""
    timed = [(e.time_utc, e) for e in events if e.time_utc is not None]
    untimed = [e for e in events if e.time_utc is None]
    return [e for _, e in sorted(timed, key=lambda pair: pair[0], reverse=True)] + untimed


class TableRows(HTMLParser):
    """Collects the text of every table row as a list of cell texts, ignoring scripts and styles."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None and not self._skip:
            self._cell.append(data)


def table_rows(html: str) -> list[list[str]]:
    parser = TableRows()
    parser.feed(html)
    parser.close()
    return parser.rows


def page_text(html: str) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)
