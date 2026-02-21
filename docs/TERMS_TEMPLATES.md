# Terms Templates

## Что добавлено

- Версионируемые шаблоны условий в таблице `terms_templates`.
- Сегментация клиента: `B2C`, `BRF`, `B2B` (`clients.client_segment`).
- Default-шаблоны в `company_profile` для OFFER и INVOICE.
- Снапшот условий при `finalize`:
  - `projects.offer_terms_snapshot_title/body`
  - `invoices.invoice_terms_snapshot_title/body`

## Правила выбора шаблона

1. Если в `company_profile` указан default для типа документа — используется он.
2. Иначе берётся последний активный шаблон по `(segment, doc_type, lang)`.
3. Если для языка нет шаблона — fallback на `sv`.

## Неизменяемость issued

После issue текст в документе читается из snapshot-полей и не меняется при последующих изменениях шаблонов.

## UI

- `/settings/terms` — список шаблонов + создание новой версии.
- Редактирование реализовано как создание новой версии из существующей (copy/version).
- `/settings/company` — выбор default шаблонов для offer/invoice.
