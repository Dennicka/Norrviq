# Ready to Work Checklist

## Implemented
- Correctness lock validations for estimate/pricing/offer/invoice critical actions.
- Duplicate draft protection for project-driven invoice drafts.
- Route integrity and i18n smoke checks for RU/SV.
- Local startup helpers: `make doctor`, `make bootstrap-local`, `make run-local`.
- Admin diagnostics page: `/admin/diagnostics`.

## Out of scope
- Major pricing/material/document engine redesign.
- Multi-tenant and external integrations.

## Daily estimator workflow
1. Create/update client.
2. Create project.
3. Add rooms and work items.
4. Recalculate estimate.
5. Select pricing mode.
6. Create offer draft -> issue offer.
7. Create invoice draft -> issue invoice.
8. Export PDFs.

## Recovery tips
- Run `make doctor` first.
- If DB appears broken, restore from `/admin/backups`.
- If correctness lock fails, open pricing/project page and fix missing/negative values.

## Backup before upgrade
- Create backup in `/admin/backups`.
- Run migrations, then smoke flow tests.

## Verify calculations after updates
- Run regression/golden tests and pricing/invoice/offer tests.

## Release checklist
- `ruff check .`
- full `pytest -q`
- verify `/admin/diagnostics`
- verify end-to-end estimator flow
