# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Fieldnotes is a minimal single-user Flask app for tracking editorial research
status ("visit" / "mixed" / "desk") and nested field notes (with photos and
GPS location) per topic. There is no user model and no login in the app
itself — auth is handled by HTTP Basic Auth in nginx in front of the app
(see README.md for the nginx/systemd deployment config on
`fieldnotes.altner.cloud`).

The whole app is intentionally three files:

- [app.py](app.py) — Flask app, SQLAlchemy models, and all API routes.
- [templates/index.html](templates/index.html) — the entire frontend: inline
  `<style>` and vanilla JS (no build step, no framework, no bundler). JS talks
  to the API with `fetch` and re-renders the whole list on every change
  (`render()` fully replaces `#list` contents — no diffing). Also loads
  Leaflet (map) from `unpkg.com` and Google Fonts, both via external URLs —
  no bundling/vendoring.
- `static/uploads/` — uploaded field-note photos, created on demand
  (`UPLOAD_FOLDER` in [app.py](app.py)); served directly by Flask's default
  static handling.

## Commands

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py          # -> http://127.0.0.1:5000, debug=True
```

There is no test suite, linter, or build step in this repo.

SQLite file `instance/fieldnotes.db` is created automatically on first run
(`db.create_all()` at import time in [app.py](app.py); Flask-SQLAlchemy puts
relative sqlite URIs under `instance/` by default). Deleting it resets all
data — there are no migrations, so schema changes require either manually
altering the DB or deleting the file and letting it regenerate. Deleting
`instance/fieldnotes.db` does **not** delete uploaded photo files in
`static/uploads/` — those need separate cleanup if you reset the DB.

## Architecture

**Data model** (in [app.py](app.py)):
- `Topic`: `title`, `status` (`"visit"` | `"mixed"` | `"desk"` | `None`),
  `gap_notes` (free text on what's editorially still missing), `done`.
- `FieldNote`: belongs to a `Topic` (cascade delete), has `date` (stored as
  an ISO string, not a `Date` column), `place` (free-text label), `lat`/`lng`
  (nullable floats — GPS coordinates), `text`, and `photos`.
- `Photo`: belongs to a `FieldNote` (cascade delete), stores only a
  `filename`; the file itself lives in `static/uploads/`. `Photo.delete_file()`
  removes the file from disk and must be called explicitly before deleting a
  `Photo`/`FieldNote`/`Topic` row — cascade deletes clean up DB rows but never
  touch the filesystem on their own (see `delete_topic`, `delete_fieldnote`,
  `delete_photo` for the pattern).
- `to_dict()` on each model is the only serialization boundary; note the
  camelCase conversion there (`gap_notes` -> `gapNotes`, `field_notes` ->
  `fieldNotes`) that the frontend JSON relies on.

**API** is a plain REST-ish surface, all under `/api/`: full list of topics
(with nested field notes, with nested photos) on `GET /api/topics`, `PATCH`
endpoints do partial updates (only apply keys present in the request body —
see `update_topic` / `update_fieldnote`), field notes are created empty via
`POST /api/topics/<id>/fieldnotes` and then filled in via `PATCH` (including
`lat`/`lng`). Photos are uploaded via `multipart/form-data` (field name
`photo`) to `POST /api/fieldnotes/<id>/photos`, capped at 10 MB
(`MAX_CONTENT_LENGTH`); allowed extensions are in `ALLOWED_PHOTO_EXTENSIONS`.

**Location capture** in [templates/index.html](templates/index.html): each
field note gets a Leaflet map (OpenStreetMap tiles) built in `render()`'s
second pass — map containers are queued in `pendingMaps` while building each
card, then `L.map(...)` is initialized only *after* all cards are appended to
the live DOM (Leaflet needs a connected, sized container; initializing while
detached silently produces a 0×0 map). Location can be set via the "Use
current location" button (`navigator.geolocation`), by clicking the map, or
by dragging the marker — all three funnel through `setFieldNoteLocation()`,
which persists `lat`/`lng` via `PATCH` and, if `place` is still empty,
auto-fills it from a Nominatim reverse-geocode call (never overwrites a
non-empty `place`).

**Frontend** keeps all topics in a single in-memory `topics` array, mutates
it directly after each API call, and calls `render()` to rebuild the DOM from
scratch — including recreating every Leaflet map instance each time. There's
no client-side router or state library — if you're adding a UI feature,
follow the existing pattern of: mutate `topics`, call the relevant API
helper, then `render()`.

When changing the API response shape, update both `to_dict()` in
[app.py](app.py) and the corresponding rendering code in
[templates/index.html](templates/index.html) — nothing enforces this contract
between them.
