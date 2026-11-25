# Fixtures

| File | Source |
| --- | --- |
| `poste_in_transit.json`, `poste_not_found.json` | Real responses, 2026-11-22, anonymised |
| `inpost_not_found.json`, `gls_not_found.html`, `brt_not_found.html` | Real responses, 2026-11-22, anonymised |
| `inpost_in_transit.json` | Real response, 2026-11-25, anonymised (number, lockers, addresses) |
| `brt_label_not_found.html`, `brt_invalid_code.html` | Real responses, 2026-11-25, fetched with fake numbers |
| `inpost_documented.json` | Built from the ShipX documentation: not a real response |
| `gls_documented.html`, `brt_documented.html` | Built from public scrapers of these pages: not real responses |

Replace each `*_documented` file with a real, anonymised response as soon as a shipment of that carrier is available.
