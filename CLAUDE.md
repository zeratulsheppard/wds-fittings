# CLAUDE.md

## What this is

WDS Fittings — a standalone alternative to Alliance Auth's fittings app.
Members import ship fits (EFT/DNA/pyfa XML/killmail), the app renders ships
and modules, computes pyfa-level stats, and mirrors corp fittings via ESI.

## Stack

- Python 3.11 · FastAPI · Uvicorn · Jinja2
- SQLite for app data (`data/fittings.db`)
- Fuzzwork SDE SQLite for game data (`data/sde/sqlite-latest.sqlite`)
- Vendored pyfa `eos` engine for stats (BSD-2, added in phase 5)

## Auth

Same header-trust model as `wds-hub`:

| Header | Content |
|---|---|
| `X-Authenticated-User` | Character name |
| `X-Character-Id` | Character ID |
| `X-Character-Roles` | Comma-separated EVE corp roles |
| `X-Character-Titles` | Comma-separated corp titles |

Injected by the WDS Hub SSO gateway on port 3007. `DEV_*` env vars stand
in during local dev — see `.env.example`.

`app/auth.py` exposes `require_user` (401 if not authenticated) and
`require_director` (403 unless Director role).

## Layout

```
app/
  main.py         — FastAPI entrypoint
  config.py       — env-driven settings
  auth.py         — SSO header trust + user model
  db.py           — SQLite connection + schema
  routes/         — HTTP routes
  templates/      — Jinja2 templates (base.html + per-page)
  static/         — CSS + assets
  parsers/        — fit import parsers (phase 3)
  sde/            — Fuzzwork SDE loader (phase 2)
  engine/         — pyfa eos wiring (phase 5)
deploy/           — systemd unit + deploy README
data/             — SQLite dbs (gitignored)
```

## Commands

```bash
pip install -r requirements.txt
python -m app.main            # dev server on :3016
```

## Deploy

`/opt/wds-fittings` on `10.0.0.33`. Service `wds-fittings.service`.
DNS+tunnel via main cloudflared tunnel `3ab5ab83`. See `deploy/README.md`.

## Conventions

- WDS branding: orange `#F07C00`, text `#ADADAD`, bg `#111`. Logo:
  `https://images.evetech.net/alliances/99006319/logo?size=128`
- Ship renders: `https://images.evetech.net/types/{type_id}/render?size=256`
- Module icons: `https://images.evetech.net/types/{type_id}/icon?size=64`
- Corp ID: `98330748`
- Never `cloudflared tunnel route dns` — always Cloudflare API directly.
