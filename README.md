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

| Carrier | Provider | Endpoint | Confirmed on real responses |
| --- | --- | --- | --- |
| Poste Italiane (`poste`) | `PosteItaliane` | `POST www.poste.it/online/dovequando/DQ-REST/ricercamultipla`, JSON, up to 10 numbers per call | not found, in transit |
| InPost (`inpost`) | `InPost` | `GET api-shipx-it.easypack24.net/v1/tracking/{number}`, JSON, no key | not found; known shipments follow the ShipX docs |
| GLS Italy (`gls`) | `Gls` | `POST www.gls-italy.com/it/servizi-per-destinatari/dettaglio-spedizione`, HTML form | not found; known shipments follow public scrapers |
| BRT (`brt`) | `Brt` | `GET vas.brt.it/vas/sped_det_show.hsm`, HTML (`Nspediz` = 12 digits, else `brtCode`); a 15-digit parcel ID (ID collo) fails at once: no public page tracks it | not found; known shipments follow public scrapers |
| Mondial Relay (`mondialrelay`) | `MondialRelay` | `GET www.mondialrelay.com/en-gb/parcel-tracking/`, HTML (`exp` = 8 digits, `ens` = sender brand, Vinted's `V1TTO` by default) | in transit, not found; pickup and delivery phrases follow the page's progress bar |
| Japan Post (`japanpost`) | `JapanPost` | `GET trackings.post.japanpost.jp/services/srv/search/direct`, HTML (`locale=en`); times local, Japan or Italy | in transit, not found; later events follow the UPU names |

`parceldesk.carriers.ALL` lists them. Each module says which shapes are confirmed and which are assumed; `src/parceldesk/fixtures/README.md` says which fixtures are real. Statuses come from the carrier's sentence through shared Italian phrases, and a sentence nobody recognises maps to `unknown`, with the original kept in `status_raw`. Providers never get past a CAPTCHA or a bot check: if a carrier adds one, the page stops matching and the provider raises `PermanentTrackingError`.

## Use

```python
from parceldesk import ParcelDesk, TrackedNumber

from parceldesk.carriers import ALL

desk = ParcelDesk([carrier() for carrier in ALL])
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
