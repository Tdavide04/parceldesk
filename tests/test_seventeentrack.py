"""17TRACK client with a fake transport and the documented responses. No network, no real waits."""
from datetime import UTC, datetime

import pytest
import requests

from parceldesk import PermanentTrackingError, Registration, SeventeenTrack, TrackedNumber, TransientTrackingError
from parceldesk.testing import FakeClock, FakeSeventeenTrack, load_fixture, provider_with, response


def test_track_parses_status_events_and_dates():
    fake = FakeSeventeenTrack({"gettrackinfo": [load_fixture("gettrackinfo")]})
    result = provider_with(fake).track([TrackedNumber("RR123456789IT", 9071), TrackedNumber("AB12345")])
    (snap,) = result.snapshots
    assert (snap.number, snap.carrier, snap.status, snap.sub_status, snap.tag) == ("RR123456789IT", 9071, "delivered", "Delivered_Other", "in:42")
    assert [e.description for e in snap.events] == ["Consegnato", "In consegna", "In transito", "Accettato"]
    assert snap.events[0].time_utc == datetime(2026, 11, 20, 10, 32, tzinfo=UTC)
    assert snap.events[2].status == "in_transit" and snap.events[2].carrier_name == "Poste Italiane"
    assert snap.delivered_at == datetime(2026, 11, 20, 10, 32, tzinfo=UTC)
    assert snap.estimated_delivery_to == datetime(2026, 11, 20, 23, 0, tzinfo=UTC)
    assert snap.events_hash == "1834721"
    assert [(r.number, r.code) for r in result.rejected] == [("AB12345", -18019902)]
    assert fake.calls[0]["json"] == [{"number": "RR123456789IT", "carrier": 9071}, {"number": "AB12345"}]
    assert fake.calls[0]["headers"]["17token"] == "test-key"


def test_unknown_statuses_stay_raw():
    payload = load_fixture("gettrackinfo")
    payload["data"]["accepted"][0]["track_info"]["latest_status"]["status"] = "Teleported"
    snap = provider_with(FakeSeventeenTrack({"gettrackinfo": [payload]})).track([TrackedNumber("RR123456789IT")]).snapshots[0]
    assert (snap.status, snap.status_raw) == ("unknown", "Teleported")


def test_register_sends_hints_and_splits_accepted_from_rejected():
    fake = FakeSeventeenTrack({"register": [load_fixture("register")]})
    result = provider_with(fake).register([Registration("RR123456789IT", tag="out:7", destination_country="IT", destination_postal_code="20100", lang="it"), Registration("AB12345")])
    assert [(a.number, a.carrier) for a in result.accepted] == [("RR123456789IT", 9071)]
    assert [(r.number, r.code) for r in result.rejected] == [("AB12345", -18019901)]
    assert fake.calls[0]["json"][0] == {"number": "RR123456789IT", "tag": "out:7", "destination_country": "IT", "destination_postal_code": "20100", "lang": "it"}


def test_batches_are_split_by_forty_and_spaced_by_the_rate_limit():
    empty = {"code": 0, "data": {"accepted": [], "rejected": []}}
    fake = FakeSeventeenTrack({"stoptrack": [empty, empty, empty]})
    clock = FakeClock()
    provider_with(fake, clock).stop([TrackedNumber(f"RR{i:09d}IT") for i in range(81)])
    assert [len(c["json"]) for c in fake.calls] == [40, 40, 1]
    assert clock.sleeps == [pytest.approx(0.35), pytest.approx(0.35)]


def test_quota():
    quota = provider_with(FakeSeventeenTrack({"getquota": [load_fixture("getquota")]})).quota()
    assert (quota.total, quota.used, quota.remaining) == (1100, 2, 1098)


def test_429_and_5xx_are_retried_then_transient():
    fake = FakeSeventeenTrack({"getquota": [response(429), response(503), load_fixture("getquota")]})
    assert provider_with(fake).quota().remaining == 1098
    fake = FakeSeventeenTrack({"getquota": [requests.ConnectionError("down")] * 4})
    with pytest.raises(TransientTrackingError, match="4 attempts"):
        provider_with(fake).quota()


def test_401_is_permanent():
    with pytest.raises(PermanentTrackingError, match="401"):
        provider_with(FakeSeventeenTrack({"getquota": [response(401)]})).quota()


def test_request_level_errors_are_permanent_with_their_code():
    body = {"code": -18019908, "data": {"errors": [{"code": -18019908, "message": "Your quotas have ran out."}]}}
    with pytest.raises(PermanentTrackingError, match="quota exhausted") as exc:
        provider_with(FakeSeventeenTrack({"register": [body]})).register([Registration("RR123456789IT")])
    assert exc.value.code == -18019908


def test_an_api_key_is_required():
    with pytest.raises(ValueError):
        SeventeenTrack("")
