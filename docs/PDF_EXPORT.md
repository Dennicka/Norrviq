# PDF export for Offer and Invoice

## Endpoints

- `GET /offers/{offer_id}/pdf`
- `GET /invoices/{invoice_id}/pdf`

Both endpoints require authenticated user with role `viewer`, `operator`, or `admin`.

Responses:
- `Content-Type: application/pdf`
- `Content-Disposition: attachment; filename="Trenor_Offer_<NUMBER>.pdf"` (or `Invoice`)
- `X-Request-Id` is propagated in response headers.

## Draft watermark

For documents in `draft` status, PDF includes a visible watermark `DRAFT / UTKAST` and explicit status in metadata.
For issued documents watermark is not shown.

- Issued offer uses snapshot terms (`offer_terms_snapshot_title/body`).
- Issued invoice uses snapshot terms (`invoice_terms_snapshot_title/body`) and stored invoice lines/totals snapshot.

## Server/CI dependencies

Python dependencies are pinned in `requirements.txt`:
- `weasyprint==62.3`
- `pypdf==5.3.0` (tests)

GitHub Actions installs required Ubuntu system packages in workflow:
- `libcairo2`
- `libpango-1.0-0`
- `libpangoft2-1.0-0`
- `libgdk-pixbuf-2.0-0`
- `libffi8`
- `shared-mime-info`
- `fonts-dejavu`

DejaVu font ensures Swedish characters `ÅÄÖ` render correctly in PDFs.
