# parceldesk

Shipment tracking for [Personal Collection Hub](https://github.com/Tdavide04/personal-collection-hub): canonical domain types, a `TrackingProvider` port with one provider per carrier, and `ParcelDesk`, which sends each number to its carrier.

Providers read the carriers' own public tracking pages over plain HTTP, as the Subito and Vinted adapters do. No aggregator and no API key. ParcelDesk translates only: the hub stores shipments and their history, polls for updates in its worker (hub ADR-0010) and shows them in the dashboard.

| Module | Contents |
| --- | --- |
| `parceldesk.domain` | `TrackedNumber`, `TrackingSnapshot`, `TrackingEvent`, canonical `Status`, `TrackingResult`, `RejectedNumber` |
| `parceldesk.provider` | The `TrackingProvider` port, `TransientTrackingError`, `PermanentTrackingError` |
| `parceldesk.http` | `CarrierHttp`: a gap between requests, retries on 429/5xx/timeouts honouring Retry-After |
| `parceldesk.desk` | `ParcelDesk` and `detect_carriers`, which gives format hints for the user to confirm |
| `parceldesk.carriers` | One provider per carrier |
| `parceldesk.testing` | Fake HTTP session, clock and provider; `load_fixture` for the real responses |

## Carriers

| Carrier | Endpoint | Status |
| --- | --- | --- |
| Poste Italiane (`poste`) | `POST www.poste.it/online/dovequando/DQ-REST/ricercamultipla`, JSON, several numbers per call | `parceldesk.carriers.PosteItaliane`; only "accepted" and "in transit" phrases confirmed so far |
| InPost (`inpost`) | `GET api-shipx-it.easypack24.net/v1/tracking/{number}`, JSON, no key | reachable, provider to write |
| GLS Italy (`gls`) | `POST www.gls-italy.com/it/servizi-per-destinatari/dettaglio-spedizione`, HTML form | reachable, provider to write |
| BRT (`brt`) | `GET vas.brt.it/vas/sped_det_show.hsm?Nspediz={number}`, HTML | reachable, provider to write |

A provider is written only from real, anonymised responses saved in `src/parceldesk/fixtures/`. Providers never get past a CAPTCHA or a bot check: when a carrier adds one, the provider raises `PermanentTrackingError`.

## Use

```python
from parceldesk import ParcelDesk, TrackedNumber

desk = ParcelDesk([poste_provider, brt_provider])
result = desk.track([TrackedNumber("RR123456789IT", "poste"), TrackedNumber("123456789012", "brt")])
for snapshot in result.snapshots:
    print(snapshot.carrier, snapshot.status, snapshot.events[0].description if snapshot.events else "-")
```

A failing carrier does not stop the others: its numbers come back in `result.rejected`, with `retryable` set when trying later may work. A number the carrier does not know yet is a snapshot with status `not_found`, not an error.

## Development

```sh
uv sync
uv run pytest
```

Licensed under MIT.
