from datetime import UTC, datetime

import pytest

from parceldesk import TrackedNumber, TrackingEvent, TrackingSnapshot, normalize_number


def test_numbers_are_upper_cased_without_spaces():
    assert normalize_number(" rr 1234 5678 9it ") == "RR123456789IT"
    assert TrackedNumber("rr123456789it", "poste").number == "RR123456789IT"


@pytest.mark.parametrize("number", ["", "1234", "A" * 51, "RR12/3456", "RR 12;34"])
def test_invalid_numbers_are_refused(number):
    with pytest.raises(ValueError):
        normalize_number(number)


def test_the_carrier_is_required():
    with pytest.raises(ValueError, match="carrier"):
        TrackedNumber("RR123456789IT", "")


def _snapshot(events):
    return TrackingSnapshot("RR123456789IT", "poste", "in_transit", "In transito", events)


def test_events_hash_changes_with_any_event():
    first = TrackingEvent("Accettata", datetime(2026, 11, 20, 9, tzinfo=UTC), location="Milano")
    moved = TrackingEvent("In transito", datetime(2026, 11, 21, 9, tzinfo=UTC), location="Bologna")
    assert _snapshot([first]).events_hash == _snapshot([first]).events_hash
    assert _snapshot([first]).events_hash != _snapshot([moved, first]).events_hash
    relocated = TrackingEvent("Accettata", first.time_utc, location="Roma")
    assert _snapshot([first]).events_hash != _snapshot([relocated]).events_hash
