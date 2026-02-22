# Invoice Lines

Invoice теперь хранит строки (`invoice_lines`) как snapshot документа.

## Что такое line items

Каждая строка содержит:
- тип (`LABOR` / `MATERIAL` / `OTHER`)
- описание для клиента
- qty/unit/unit price
- pre-calculated totals (`line_total_ex_vat`, `vat_amount`, `line_total_inc_vat`)
- optional source (`WORK_ITEM` / `MATERIAL` / `MANUAL` + `source_id`)

Итоги инвойса (`subtotal_ex_vat`, `vat_total`, `total_inc_vat`) считаются только через сервис `recalculate_invoice_totals`.

## Генерация из проекта

Endpoint:
`POST /projects/{project_id}/invoices/{invoice_id}/generate-lines`

Параметры:
- `include_labor` (default `true`)
- `include_materials` (default `false`)
- `merge_strategy`:
  - `REPLACE_ALL`
  - `APPEND`
  - `UPSERT_BY_SOURCE`

Для labor generator использует `project_work_items`.

## Merge strategies

- `REPLACE_ALL`: удаляет текущие строки и создаёт заново.
- `APPEND`: добавляет сгенерированные строки в конец.
- `UPSERT_BY_SOURCE`: обновляет строки с тем же `source_type/source_id`, остальные добавляет.

## Почему fixed mode = одна строка в v1

Для `FIXED_TOTAL`, `PER_M2`, `PER_ROOM` в v1 используется одна строка `Fixed price (labour)`.
Это даёт юридически стабильный snapshot без сложного распределения fixed суммы по нормам.
