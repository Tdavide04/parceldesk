"""Fakes for this package's tests and for the hub's: a scripted HTTP session, a clock and a fake provider.

    from parceldesk.testing import FakeProvider, snapshot
    desk = ParcelDesk([FakeProvider("poste", {"RR123456789IT": snapshot("RR123456789IT", "poste", "delivered")})])
"""
import json
from importlib.resources import files
from typing import Any

import requests

from parceldesk.domain import Status, TrackingEvent, TrackingSnapshot


def load_fixture(name: str) -> Any:
    """A carrier response shipped with the package (see src/parceldesk/fixtures/README.md): JSON parsed, HTML as text."""
    folder = files("parceldesk").joinpath("fixtures")
    if folder.joinpath(f"{name}.json").is_file():
        return json.loads(folder.joinpath(f"{name}.json").read_text(encoding="utf-8"))
    raw = folder.joinpath(f"{name}.html").read_bytes()
    return raw.decode("utf-8") if b"charset=iso-8859" not in raw[:2000].lower() else raw.decode("iso-8859-15")


def response(status: int, body: object = None, text: str | None = None, headers: dict[str, str] | None = None) -> requests.Response:
    """A JSON response, or an HTML one when `text` is given."""
    r = requests.Response()
    r.status_code = status
    if text is not None:
        r._content = text.encode()
        r.headers["Content-Type"] = "text/html; charset=utf-8"
        r.encoding = "utf-8"
    else:
        r._content = json.dumps(body if body is not None else {}).encode()
        r.headers["Content-Type"] = "application/json"
    r.headers.update(headers or {})
    return r


class FakeSession:
    """Answers from a script of Responses or exceptions, in order, and records every call."""

    def __init__(self, script: list[Any]):
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.script:
            raise AssertionError(f"unexpected {method} {url}")
        outcome = self.script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def snapshot(number: str, carrier: str, status: Status = "in_transit", events: list[TrackingEvent] | None = None) -> TrackingSnapshot:
    return TrackingSnapshot(number=number, carrier=carrier, status=status, status_raw=status, events=events or [])


class FakeProvider:
    """A provider answering from a dict; numbers it does not hold are left out of the answer."""

    def __init__(self, carrier: str, answers: dict[str, TrackingSnapshot] | None = None, max_batch: int = 10, error: Exception | None = None):
        self.carrier = carrier
        self.max_batch = max_batch
        self.answers = answers or {}
        self.error = error
        self.batches: list[list[str]] = []

    def track(self, numbers: list[str]) -> list[TrackingSnapshot]:
        self.batches.append(list(numbers))
        if self.error is not None:
            raise self.error
        return [self.answers[n] for n in numbers if n in self.answers]


