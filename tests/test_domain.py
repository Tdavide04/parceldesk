import pytest

from parceldesk import Registration, TrackedNumber, normalize_number


def test_numbers_are_upper_cased_without_spaces():
    assert normalize_number(" rr 1234 5678 9it ") == "RR123456789IT"
    assert TrackedNumber("rr123456789it").number == "RR123456789IT"


@pytest.mark.parametrize("number", ["", "1234", "A" * 51, "RR12/3456", "RR 12;34"])
def test_invalid_numbers_are_refused(number):
    with pytest.raises(ValueError):
        normalize_number(number)


def test_registration_checks_its_hints():
    with pytest.raises(ValueError, match="tag"):
        Registration("RR123456789IT", tag="x" * 101)
    with pytest.raises(ValueError, match="ISO"):
        Registration("RR123456789IT", destination_country="Italy")
    assert Registration("RR123456789IT", carrier=9071, destination_country="IT").carrier == 9071
