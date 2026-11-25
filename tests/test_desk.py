import pytest

from parceldesk import ParcelDesk, PermanentTrackingError, TrackedNumber, TransientTrackingError, detect_carriers
from parceldesk.testing import FakeProvider, snapshot


def test_sends_each_number_to_its_carrier_in_batches():
    poste = FakeProvider("poste", {n: snapshot(n, "poste") for n in ("RR000000001IT", "RR000000002IT", "RR000000003IT")}, max_batch=2)
    brt = FakeProvider("brt", {"123456789012": snapshot("123456789012", "brt", "delivered")})
    desk = ParcelDesk([poste, brt])
    result = desk.track([
        TrackedNumber("RR000000001IT", "poste"), TrackedNumber("123456789012", "brt"),
        TrackedNumber("RR000000002IT", "poste"), TrackedNumber("RR000000003IT", "poste"),
        TrackedNumber("rr000000001it", "poste"),
    ])
    assert poste.batches == [["RR000000001IT", "RR000000002IT"], ["RR000000003IT"]]
    assert brt.batches == [["123456789012"]]
    assert len(result.snapshots) == 4 and result.rejected == []


def test_a_failing_carrier_does_not_stop_the_others():
    desk = ParcelDesk([
        FakeProvider("gls", error=TransientTrackingError("gls: HTTP 503")),
        FakeProvider("inpost", error=PermanentTrackingError("inpost: page changed")),
        FakeProvider("poste", {"RR000000001IT": snapshot("RR000000001IT", "poste")}),
    ])
    result = desk.track([
        TrackedNumber("Y1550012467", "gls"), TrackedNumber("1" * 24, "inpost"), TrackedNumber("RR000000001IT", "poste"),
    ])
    assert [s.number for s in result.snapshots] == ["RR000000001IT"]
    assert {(r.carrier, r.retryable) for r in result.rejected} == {("gls", True), ("inpost", False)}


def test_numbers_without_provider_or_answer_are_rejected():
    desk = ParcelDesk([FakeProvider("poste")])
    result = desk.track([TrackedNumber("RR000000001IT", "poste"), TrackedNumber("123456789012", "dhl")])
    assert {(r.number, r.retryable) for r in result.rejected} == {("RR000000001IT", True), ("123456789012", False)}


def test_one_provider_per_carrier():
    with pytest.raises(ValueError, match="two providers"):
        ParcelDesk([FakeProvider("poste"), FakeProvider("poste")])


@pytest.mark.parametrize(("number", "expected"), [
    ("RR123456789IT", ["poste"]),
    ("1" * 24, ["inpost"]),
    ("Y1550012467", ["gls"]),
    ("123456789012", ["brt", "gls", "poste"]),
    ("12345678", ["mondialrelay"]),
    ("1" * 14, ["brt"]),
    ("ABC", None),
    ("ZZ-1234567", []),
])
def test_detection_gives_hints(number, expected):
    if expected is None:
        with pytest.raises(ValueError):
            detect_carriers(number)
    else:
        assert detect_carriers(number) == expected
