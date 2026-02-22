# Invoicing flow

## 1) Create invoice from project

On the project page, use **Create invoice** to create (or reuse) a draft invoice for the project.

- Endpoint: `POST /projects/{project_id}/invoices/create-from-project`
- Options:
  - `include_labor` (default `true`)
  - `include_materials` (default `false`)
  - `merge_strategy` (default `REPLACE_ALL`)
  - `note` (optional)
- Idempotency:
  - server enforces one active `draft` invoice per source project
  - repeated click returns the same draft instead of creating duplicates

## 2) Edit draft lines

After creation the system generates invoice lines from project data, recalculates totals, and opens the invoice document page.

Draft can still be edited:

- regenerate lines with selected merge strategy
- add/remove/update individual lines
- totals are recalculated from current lines

## 3) Finalize (Issue)

Finalize/issue rules are unchanged:

- `draft` invoice is editable
- issue is blocked by existing quality gates:
  - floor checks
  - sanity checks
  - completeness checks

These validations run as before and must pass before invoice is issued.
