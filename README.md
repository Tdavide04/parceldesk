# parceldesk

Shipment tracking for [Personal Collection Hub](https://github.com/Tdavide04/personal-collection-hub): canonical domain types, a `TrackingProvider` port and a client for the [17TRACK Tracking API v2.4](https://api.17track.net/en/doc).

It translates only: no persistence, scheduling or notifications. The hub stores shipments and their event history, polls for updates in its worker (17TRACK refreshes every 6–12 hours, so no webhook is needed: hub ADR-0010) and shows them in the dashboard.

| Module | Contents |
| --- | --- |
| `parceldesk.domain` | `TrackedNumber`, `Registration`, `TrackingSnapshot`, `TrackingEvent`, canonical `Status`, batch results |
| `parceldesk.provider` | The `TrackingProvider` port, `TransientTrackingError`, `PermanentTrackingError` |
| `parceldesk.seventeentrack` | `SeventeenTrack`: register, track (polling `gettrackinfo`), stop, reactivate, quota; batches of 40, 3 requests per second, retries on 429/5xx |
| `parceldesk.testing` | Fake 17TRACK transport and example responses |

## Use

```python
from parceldesk import Registration, SeventeenTrack, TrackedNumber

tracker = SeventeenTrack(api_key)
tracker.register([Registration("RR123456789IT", carrier=9071, tag="in:42", lang="it")])
for snapshot in tracker.track([TrackedNumber("RR123456789IT", 9071)]).snapshots:
    print(snapshot.status, snapshot.events[0].description)
```

Batch calls can succeed for some numbers and fail for others: check `rejected` in every result. Registering costs 17TRACK quota once per number; reading does not start new tracking.

## Caveats

The example responses in `src/parceldesk/fixtures/` are built from the documented schema, not captured from the API. Replace them with real, anonymised responses once an API key is available. Open points about the API (which calls cost quota, provider order, `cacheLevel` format) are listed in the hub's `docs/research/17track-api.md`.

## Development

```sh
uv sync
uv run pytest
```

Licensed under MIT.
