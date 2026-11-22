# parceldesk

Shipment tracking library for Personal Collection Hub. Decisions live in the hub repo (`docs/adr/`): ADR-0010 (polling instead of webhooks) and ADR-0012 (a library: database, worker, API and dashboard stay in the hub). Domain terms (Spedizione, Direzione, Ferma, Riattivazione) are in the hub's `GLOSSARY.md`.

Source code, identifiers, commit messages and `README.md` are in English. Talk to the user in Italian.

Tracking comes from each carrier's own public pages (Poste Italiane, InPost, GLS, BRT), one provider per carrier; 17TRACK was rejected because it is business-only. Write a provider only from real responses saved as fixtures, with tracking numbers, names and addresses replaced by fake values. Never get past a CAPTCHA or a bot check.
