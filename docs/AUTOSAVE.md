# Autosave and resilient forms

## Where autosave is enabled

- Room form (`/projects/{id}/rooms/create`, `/projects/{id}/rooms/{room_id}/edit`).
- Work item edit form (`/projects/{id}/items/{item_id}/edit`).
- Project pricing (`/projects/{id}/pricing`).
- Project buffers/speed profile (`/projects/{id}/buffers`).
- Company profile page keeps local drafts only (`/settings/company`).

## How it works

- Debounced save is triggered ~1 second after the last input change.
- Browser first stores a local draft in `localStorage` with key format:
  - `draft:<entity>:<id>:<fieldhash>`
- If endpoint exists, frontend sends `PATCH` JSON with CSRF header (`X-CSRF-Token`).
- Status indicator values:
  - `Saving…`
  - `Saved`
  - `Offline / retrying…`
  - `Error: ...`

## Draft restore

- On page open, if local draft timestamp is newer than form `data-server-updated-at`, user sees `Restore draft?`.
- Buttons:
  - `Restore` applies draft values to fields.
  - `Discard` removes local draft.

## Backend JSON contract

Validation error:

```json
{ "error": "validation", "fields": { "floor_area_m2": "Must be > 0" }, "request_id": "..." }
```

Success:

```json
{ "ok": true, "updated_at": "...", "request_id": "..." }
```

## Security and auditing

- PATCH endpoints require role `operator` or `admin`.
- CSRF check is mandatory (global dependency).
- Audit event `draft_autosave` is written per successful autosave.
- Structured logs include status and `request_id` and never include field values.
