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

- [x] Scaffold: FastAPI, WDS branding, EVE SSO (corp gate), SQLite, systemd
- [x] Fuzzwork SDE loader + weekly auto-refresh timer
- [x] Import parsers (EFT, DNA, pyfa XML, killmail)
- [x] Fit view: in-game style row layout with CCP slot icons
- [x] Tags, browse-page filters, search, ship-group filter
- [x] Edit fit (name / description / optional body replacement)
- [ ] Pyfa-level stats — deferred; vendoring pyfa's eos would take 15-25 hrs
      and carry ongoing maintenance cost. Revisit if / when the corp needs it.
