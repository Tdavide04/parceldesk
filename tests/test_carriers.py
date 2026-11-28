"""InPost, GLS and BRT. Not-found pages are real; known shipments come from `*_documented` fixtures (assumed shapes)."""
from datetime import UTC, datetime

import pytest

from parceldesk import CarrierHttp, ParcelDesk, PermanentTrackingError, TrackedNumber
from parceldesk.carriers import ALL, Brt, Gls, InPost, MondialRelay
from parceldesk.carriers._common import local_time, status_of
from parceldesk.carriers.gls import code_type
from parceldesk.testing import FakeClock, FakeSession, load_fixture, response


def make(cls, *responses):
    clock = FakeClock()
    session = FakeSession(list(responses))
    return cls(CarrierHttp(cls.carrier, session=session, clock=clock.clock, sleep=clock.sleep)), session


# --- InPost ---------------------------------------------------------------------------------------

def test_inpost_unknown_number_is_not_found():
    provider, session = make(InPost, response(404, load_fixture("inpost_not_found")))
    [snapshot] = provider.track(["000000000000000000000001"])
    assert (snapshot.status, snapshot.events) == ("not_found", [])
    assert session.calls[0]["url"].endswith("/v1/tracking/000000000000000000000001")


def test_inpost_documented_delivery():
    provider, _ = make(InPost, response(200, load_fixture("inpost_documented")))
    [snapshot] = provider.track(["000000000000000000000002"])
    assert (snapshot.status, snapshot.status_raw) == ("delivered", "delivered")
    assert [e.status for e in snapshot.events] == ["delivered", "available_for_pickup", "out_for_delivery", "in_transit", "info_received"]
    assert snapshot.events[0].description == "Consegnata"
    assert snapshot.delivered_at == datetime(2026, 11, 20, 15, 2, 11, tzinfo=UTC)
    assert snapshot.events[3].location == "MI1"


def test_inpost_unknown_status_code_is_kept():
    payload = {"status": "something_new", "tracking_details": [{"status": "something_new", "datetime": "2026-11-20T10:00:00+01:00"}]}
    provider, _ = make(InPost, response(200, payload))
    [snapshot] = provider.track(["000000000000000000000003"])
    assert (snapshot.status, snapshot.status_raw, snapshot.events[0].description) == ("unknown", "something_new", "something new")


# --- GLS ------------------------------------------------------------------------------------------

def test_gls_unknown_number_is_not_found():
    provider, session = make(Gls, response(200, text=load_fixture("gls_not_found")))
    [snapshot] = provider.track(["Y1000000001"])
    assert snapshot.status == "not_found"
    assert session.calls[0]["data"]["tipo_codice"] == "nazionale"


def test_gls_documented_delivery_newest_first():
    provider, _ = make(Gls, response(200, text=load_fixture("gls_documented")))
    [snapshot] = provider.track(["Y1000000001"])
    assert snapshot.status == "delivered"
    assert [e.description for e in snapshot.events] == ["CONSEGNATA", "IN CONSEGNA", "ARRIVATA IN SEDE", "PARTITA"]
    assert snapshot.events[0].location == "BOLOGNA"
    assert snapshot.events[0].time_utc == datetime(2026, 11, 20, 13, 32, tzinfo=UTC)


def test_gls_page_without_table_or_message_is_permanent():
    provider, _ = make(Gls, response(200, text="<html><body>Manutenzione</body></html>"))
    with pytest.raises(PermanentTrackingError):
        provider.track(["Y1000000001"])


@pytest.mark.parametrize(("number", "kind"), [("Y1550012467", "nazionale"), ("53260112365", "internazionale"), ("35638867", "id_collo")])
def test_gls_code_type(number, kind):
    assert code_type(number) == kind


# --- BRT ------------------------------------------------------------------------------------------

def test_brt_unknown_number_is_not_found():
    provider, session = make(Brt, response(200, text=load_fixture("brt_not_found")))
    [snapshot] = provider.track(["123456789012"])
    assert snapshot.status == "not_found"
    assert session.calls[0]["params"]["Nspediz"] == "123456789012"


def test_brt_long_codes_go_in_brt_code():
    provider, session = make(Brt, response(200, text=load_fixture("brt_not_found")))
    provider.track(["0000000000000000001"])
    assert session.calls[0]["params"]["brtCode"] == "0000000000000000001"


def test_brt_parcel_id_fails_at_once_without_a_request():
    provider, session = make(Brt)
    with pytest.raises(PermanentTrackingError, match="ID collo"):
        provider.track(["000000000000001"])
    assert session.calls == []


def test_brt_documented_delivery():
    provider, _ = make(Brt, response(200, text=load_fixture("brt_documented")))
    [snapshot] = provider.track(["123456789012"])
    assert [e.status for e in snapshot.events] == ["delivered", "out_for_delivery", "in_transit", "in_transit"]
    assert snapshot.events[0].time_local == "2026-11-20T12:05:00+01:00"
    assert snapshot.delivered_at == datetime(2026, 11, 20, 11, 5, tzinfo=UTC)


# --- Mondial Relay -------------------------------------------------------------------------------

def test_mondial_relay_reads_the_days_and_steps_newest_first():
    provider, session = make(MondialRelay, response(200, text=load_fixture("mondialrelay_in_transit")))
    [snapshot] = provider.track(["10000000"])
    assert session.calls[0]["params"] == {"ens": "V1TTO", "exp": "10000000", "language": "EN"}
    assert (snapshot.status, snapshot.status_raw) == ("in_transit", "Parcel shipped from the site HERMES DE")
    assert snapshot.events[0].time_local == "2026-11-27T15:49:00+01:00"
    assert snapshot.events[-1].description == "Parcel in preparation at the sender"
    assert snapshot.events[-1].status == "info_received"
    assert "Colis expédié depuis le site logisitique" in [e.description for e in snapshot.events]
    assert [e.time_utc for e in snapshot.events] == sorted((e.time_utc for e in snapshot.events), reverse=True)


def test_mondial_relay_unknown_number_is_not_found():
    provider, _ = make(MondialRelay, response(200, text=load_fixture("mondialrelay_not_found")))
    assert provider.track(["10000000"])[0].status == "not_found"


def test_mondial_relay_page_without_events_or_form_has_changed():
    provider, _ = make(MondialRelay, response(200, text="<html><body>Maintenance</body></html>"))
    with pytest.raises(PermanentTrackingError, match="changed"):
        provider.track(["10000000"])


@pytest.mark.parametrize(("phrase", "status"), [
    ("Parcel picked up in the Pudo", "in_transit"), ("Parcel delivered to Mondial Relay", "unknown"),
    ("Parcel available at the Point Relais (pickup point)", "available_for_pickup"), ("Delivered parcel", "delivered"),
    ("Parcel picked up by the recipient", "delivered"),
])
def test_mondial_relay_phrases(phrase, status):
    from parceldesk.carriers.mondialrelay import status_of as mondial_status

    assert mondial_status(phrase) == status


# --- shared ---------------------------------------------------------------------------------------

@pytest.mark.parametrize(("phrase", "status"), [
    ("CONSEGNATA", "delivered"), ("Spedizione non consegnata: destinatario assente", "delivery_failure"),
    ("IN CONSEGNA", "out_for_delivery"), ("In giacenza presso la filiale", "available_for_pickup"),
    ("PARTITA", "in_transit"), ("Dati ricevuti dal mittente", "info_received"), ("RESO AL MITTENTE", "exception"),
    ("???", "unknown"),
])
def test_phrases(phrase, status):
    assert status_of(phrase) == status


def test_local_time_handles_summer_and_two_digit_years():
    assert local_time("01/07/26", "10:00")[0] == datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    assert local_time("not a date") == (None, None)


def test_all_carriers_behind_one_desk():
    desk = ParcelDesk([make(cls)[0] for cls in ALL])
    assert desk.carriers == ("poste", "inpost", "gls", "brt", "mondialrelay")
    result = ParcelDesk([make(Brt, response(503), response(503), response(503), response(503))[0]]).track([TrackedNumber("123456789012", "brt")])
    assert result.rejected[0].retryable
