# Data Quality checks

Система использует таблицу `sanity_rules` как источник правил проверки входных данных.

## Что проверяется

- Параметры комнаты: высота, площади, длины, соотношения.
- Параметры работ: quantity, difficulty_factor.
- Параметры проекта: количество комнат, количество работ, почасовая ставка компании.

## Severity

- `WARNING`: показывается в UI, но не блокирует выпуск документов.
- `BLOCK`: критическая аномалия. Блокирует finalize Offer/Invoice (HTTP 409 для JSON).

## Где видно

- Inline feedback на сохранении комнат/работ (flash warning/error).
- Quality panel на странице проекта с кнопками `Go fix`.
- Жёсткий gate перед finalize в `/offers/{project_id}/finalize` и `/invoices/{invoice_id}/finalize`.

## Управление правилами

- `/settings/sanity-rules` (только admin).
- Изменения пишут audit event `sanity_rule_updated`.
- Блокировка выпуска документа пишет `issue_blocked_document_issue`.
