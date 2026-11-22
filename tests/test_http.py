import pytest
import requests

from parceldesk import CarrierHttp, PermanentTrackingError, TransientTrackingError
from parceldesk.testing import FakeClock, FakeSession, response

URL = "https://carrier.example/track"


def http(script, **options):
    clock = FakeClock()
    session = FakeSession(script)
    return CarrierHttp("test", session=session, clock=clock.clock, sleep=clock.sleep, **options), session, clock


def test_returns_expected_statuses_and_sends_its_user_agent():
    client, session, _ = http([response(404, {"message": "not found"})])
    assert client.request("GET", URL, expected=(200, 404)).status_code == 404
    assert session.calls[0]["headers"]["User-Agent"].startswith("parceldesk/")


def test_keeps_a_gap_between_requests():
    client, _, clock = http([response(200), response(200)], min_interval_s=2.0)
    client.request("GET", URL)
    client.request("GET", URL)
    assert clock.sleeps == [2.0]


def test_retries_429_honouring_retry_after_then_5xx_with_backoff():
    client, session, clock = http(
        [response(429, headers={"Retry-After": "7"}), response(503), response(200)], min_interval_s=0, backoff_s=1.0
    )
    assert client.request("GET", URL).status_code == 200
    assert clock.sleeps == [7.0, 2.0]
    assert len(session.calls) == 3


def test_gives_up_as_transient_after_its_retries():
    client, _, _ = http([requests.Timeout()] * 3, max_retries=2, min_interval_s=0)
    with pytest.raises(TransientTrackingError, match="3 attempts"):
        client.request("GET", URL)


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_unexpected_client_errors_are_permanent(status):
    client, session, _ = http([response(status)])
    with pytest.raises(PermanentTrackingError, match=str(status)):
        client.request("GET", URL)
    assert len(session.calls) == 1
