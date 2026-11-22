"""Fake 17TRACK transport and documented example responses, for this package's tests and for the hub's.

    from parceldesk.testing import FakeSeventeenTrack, provider_with
    fake = FakeSeventeenTrack({"gettrackinfo": [load_fixture("gettrackinfo")]})
    result = provider_with(fake).track([TrackedNumber("RR123456789IT")])
"""
import json
from importlib.resources import files
from typing import Any

import requests

from parceldesk.seventeentrack import SeventeenTrack

FIXTURE_NAMES = ("gettrackinfo", "register", "getquota")


def load_fixture(name: str) -> dict[str, Any]:
    if name not in FIXTURE_NAMES:
        raise ValueError(f"unknown fixture {name!r}")
    return json.loads(files("parceldesk").joinpath("fixtures", f"{name}.json").read_text())


def response(status: int, body: object = None) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(body if body is not None else {}).encode()
    r.headers["Content-Type"] = "application/json"
    return r


class FakeSeventeenTrack:
    """Answers each endpoint from its own script: a payload dict (HTTP 200), a Response, or an exception."""

    def __init__(self, scripts: dict[str, list[Any]]):
        self.scripts = {endpoint: list(items) for endpoint, items in scripts.items()}
        self.calls: list[dict[str, Any]] = []

    def request(self, method, url, json=None, headers=None, timeout=None):
        endpoint = url.rsplit("/", 1)[1]
        self.calls.append({"method": method, "endpoint": endpoint, "json": json, "headers": headers})
        script = self.scripts.get(endpoint)
        if not script:
            raise AssertionError(f"unexpected call to {endpoint}")
        outcome = script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome if isinstance(outcome, requests.Response) else response(200, outcome)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def provider_with(session: Any, clock: FakeClock | None = None, **options: Any) -> SeventeenTrack:
    clock = clock or FakeClock()
    return SeventeenTrack("test-key", session=session, clock=clock.clock, sleep=clock.sleep, **options)
