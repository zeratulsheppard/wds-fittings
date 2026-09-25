# wds-fittings

WDS ship fittings library — import EFT / DNA / pyfa XML / killmail fits,
render ship + module images, compute pyfa-level stats, and mirror corp
fittings from ESI.

- **URL:** https://fittings.deliverynetwork.space
- **Server:** `/opt/wds-fittings` on `10.0.0.33`, port `3016`
- **Auth:** WDS SSO gateway header trust (same pattern as wds-hub)
- **Stack:** Python 3.11 · FastAPI · Jinja2 · SQLite · Fuzzwork SDE · pyfa `eos`

## Local dev

```bash
python -m venv .venv
.venv\Scripts\activate  # PowerShell
pip install -r requirements.txt
copy .env.example .env
python -m app.main
```

Then hit http://localhost:3016 — `DEV_*` env vars stand in for the SSO gateway.

## Deploy

See [`deploy/README.md`](deploy/README.md).

## Roadmap

- [x] Phase 1 — Scaffold: FastAPI, WDS branding, SSO trust, SQLite, systemd
- [ ] Phase 2 — SDE loader (Fuzzwork SQLite)
- [ ] Phase 3 — Import parsers (EFT, DNA, pyfa XML, killmail)
- [ ] Phase 4 — Fit view with ship render + slot layout
- [ ] Phase 5 — Vendor pyfa `eos` for pyfa-level stats
- [ ] Phase 6 — Corp-shared fits: opt-in read of Fitting Managers' personal fits (`esi-fittings.read_fittings.v1`)
- [ ] Phase 7 — Search, tags/doctrines, edit UI
