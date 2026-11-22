from datetime import UTC, datetime

import pytest

from parceldesk import CarrierHttp, ParcelDesk, PermanentTrackingError, TrackedNumber
from parceldesk.carriers import PosteItaliane
from parceldesk.carriers.poste import URL, status_of
from parceldesk.testing import FakeClock, FakeSession, load_fixture, response


def poste(*responses):
    clock = FakeClock()
    session = FakeSession(list(responses))
    return PosteItaliane(CarrierHttp("poste", session=session, clock=clock.clock, sleep=clock.sleep)), session


def test_sends_the_whole_batch_in_one_post():
    provider, session = poste(response(200, load_fixture("poste_in_transit") + load_fixture("poste_not_found")))
    provider.track(["1PD0FAKE00001", "1PD0FAKE00002"])
    call = session.calls[0]
    assert (call["method"], call["url"]) == ("POST", URL)
    assert call["json"] == {"tipoRichiedente": "WEB", "listaCodici": ["1PD0FAKE00001", "1PD0FAKE00002"]}


def test_parses_a_shipment_in_transit_newest_event_first():
    provider, _ = poste(response(200, load_fixture("poste_in_transit")))
    [snapshot] = provider.track(["1PD0FAKE00001"])
    assert (snapshot.number, snapshot.carrier, snapshot.status) == ("1PD0FAKE00001", "poste", "in_transit")
    assert snapshot.status_raw == "la spedizione è in transito"
    assert [e.description for e in snapshot.events] == [
        "la spedizione è in transito", "la spedizione è stata presa in carico presso il Punto Poste-Locker",
    ]
    newest, oldest = snapshot.events
    assert newest.time_utc == datetime.fromtimestamp(1795198536, tz=UTC)
    assert newest.time_local.endswith("+01:00")
    assert (oldest.location, oldest.status) == ("TABACCHERIA ESEMPIO", "in_transit")
    assert snapshot.estimated_delivery == "Consegna prevista entro lunedì 30 novembre 2026"
    assert snapshot.delivered_at is None


def test_an_unknown_number_is_not_found_not_an_error():
    provider, _ = poste(response(200, load_fixture("poste_not_found")))
    [snapshot] = provider.track(["1PD0FAKE00002"])
    assert (snapshot.status, snapshot.events, snapshot.status_raw) == ("not_found", [], None)


@pytest.mark.parametrize(("phrase", "status"), [
    ("la spedizione è in transito", "in_transit"),
    ("La spedizione è stata consegnata", "delivered"),
    ("la spedizione non è stata consegnata", "delivery_failure"),
    ("la spedizione è in consegna", "out_for_delivery"),
    ("Qualcosa di nuovo", "unknown"),
])
def test_phrases_map_to_canonical_statuses(phrase, status):
    assert status_of(phrase) == status


def test_a_non_json_answer_is_permanent():
    provider, _ = poste(response(200, text="<html>maintenance</html>"))
    with pytest.raises(PermanentTrackingError):
        provider.track(["1PD0FAKE00001"])


def test_works_behind_the_desk():
    provider, _ = poste(response(200, load_fixture("poste_in_transit")))
    result = ParcelDesk([provider]).track([TrackedNumber("1pd0fake00001", "poste")])
    assert [s.status for s in result.snapshots] == ["in_transit"] and result.rejected == []
