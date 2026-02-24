# Project Workflow

`/projects/{project_id}/workflow` is the unified estimator control center for Project → Estimate → Offer → Invoice.

## Steps
1. Project data
2. Rooms & works
3. Estimate & pricing
4. Offer
5. Invoice

Each step has status: `done`, `warning`, `blocked` with localized message keys.

## Readiness rules
Implemented in `app/services/workflow.py` via `build_project_workflow_state`.

Checks include:
- project/client basics
- rooms/work items existence and quality blockers
- pricing selection and completeness for fixed mode
- company profile and pricing for offer
- offer gate before invoice + reusable draft invoice detection

## Actions
Workflow action endpoints wrap existing services and redirect back to workflow:
- `POST /projects/{project_id}/workflow/recalculate`
- `POST /projects/{project_id}/workflow/select-pricing-mode`
- `POST /projects/{project_id}/workflow/create-offer-draft`
- `POST /projects/{project_id}/workflow/create-invoice-draft`

Safety checks prevent invalid transitions and show explicit flash messages.

## Extending
Add a new step by extending `WorkflowStep` assembly and exposing extra blocks in `projects/workflow.html`.
