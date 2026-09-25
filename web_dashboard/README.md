# Lionel dashboard — trial UI shell

> **Trial UI files. No real authentication, no real data.** These pages are a
> static visual shell only. Nothing here talks to the Python agent and no
> request leaves your machine.

## How to open

Open `login.html` straight from disk (double-click it, or paste the file path
into a browser). The shell works from `file://` because `app.js` carries an
embedded mirror of `mock_data.json` — browsers block `fetch()` of a sibling file
on `file://`, so the mirror is the fallback.

To exercise the real `fetch("mock_data.json")` path, serve the folder instead:

```powershell
cd D:\Phantom-agent\web_dashboard
python -m http.server 8080
# then open http://127.0.0.1:8080/login.html
```

## Trial credentials

| Field | Value |
| --- | --- |
| Email | `trial@lionel.local` |
| Password | `letmein` |

These exist only so the sign-in screen has something to check against. Do not
reuse this password shape anywhere real.

## Files

| File | Purpose |
| --- | --- |
| `login.html` | Centered sign-in card with the trial warning banner. |
| `dashboard.html` | App shell: grouped sidebar, header, status cards, tables, charts. |
| `styles.css` | Theme variables (light/dark) plus every component style. |
| `app.js` | Login flow, dashboard guard, theme toggle, rendering, inline SVG charts. |
| `mock_data.json` | The fake users / sessions / providers payload. |
| `README.md` | This file. |

## What is fake, and what actually works

- **Derived from `mock_data.json`:** Recent Sessions rows, Provider Health rows,
  the avatar letter, the display name and the email.
- **Static in `dashboard.html`:** the four status cards (12 sessions, 1,204
  requests, 482k / 2M tokens, 0.4% errors) — `mock_data.json` has no summary
  object to drive them.
- **Generated in `app.js`:** the two chart series (`TOKEN_SERIES`,
  `REQUEST_SERIES`), which stand in for the future tokens/summary endpoint.
- **Real behaviour:** sign-in validation, dashboard guard, sign-out, theme
  toggle with `localStorage` persistence, navigation filter, and the content
  search (it filters the already-loaded rows only).

## Theme

Dark is the default. The header toggle switches `theme-dark` / `theme-light` on
`<body>` (mirrored onto `<html>` before first paint to avoid a flash), and the
choice is stored under `lionel_theme`.

## Session storage

`lionel_user` holds `{email, name, signedInAt}` only — the password is never
stored. `lionel_remembered_email` remembers the email when "Remember me" is
ticked.

## Navigation

The sidebar is visual only in this shell: clicking an item moves the highlight
and retitles the header. Every view renders the Overview panels, because no
other view exists yet.

## Before any real use, build the FastAPI backend

See the TODO comment block at the top of `app.js` for the endpoints needed:

```
GET  /api/sessions
GET  /api/providers
GET  /api/tokens/summary
POST /api/login
```

To connect this UI to the real agent you would need to:

1. Build a FastAPI app in `D:\Phantom-agent\api\`.
2. Implement endpoints that read from `audit/ledger.py`, `providers/router.py`
   and the `memory/` stores, behind the existing role/policy checks.
3. Replace every `mock_data.json` / `FALLBACK_MOCK` read in `app.js` with
   `fetch()` calls to those endpoints, and swap the trial sign-in for real
   session handling.

## Constraints honoured

- No frameworks, no npm, no CDN, no build step: plain HTML, CSS and JavaScript.
- No backend, no Python changes: this folder is self-contained.
- Secrets: `mock_data.json` holds a fake password for the trial user only. Do
  not put real credentials in these files.
