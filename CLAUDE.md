# parceldesk

Shipment tracking library for Personal Collection Hub. Decisions live in the hub repo (`docs/adr/`): ADR-0010 (polling instead of webhooks) and ADR-0012 (a library: database, worker, API and dashboard stay in the hub). Domain terms (Spedizione, Direzione, Ferma, Riattivazione) are in the hub's `GLOSSARY.md`.

Source code, identifiers, commit messages and `README.md` are in English. Talk to the user in Italian.

Fixtures are built from the 17TRACK documentation until real responses are available: say so whenever a test depends on a shape the API has not confirmed.
