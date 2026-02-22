# Document Regression Suite

Этот набор тестов фиксирует регрессии в документных рендерах:

- HTML страницы оферты/инвойса (draft и issued).
- PDF smoke (валидный `%PDF` + ключевые тексты и totals).

## Что именно фиксируем

HTML snapshots в `tests/snapshots/`:

- `offer_draft.html`
- `offer_issued_fixed_total.html`
- `offer_issued_per_m2.html`
- `offer_issued_per_room.html`
- `offer_issued_piecework.html`
- `invoice_draft.html`
- `invoice_issued_fixed_total_rot_off.html`
- `invoice_issued_per_m2_rot_off.html`
- `invoice_issued_per_room_rot_off.html`
- `invoice_issued_piecework_rot_on.html`

Перед сравнением HTML проходит через общий нормализатор `tests/utils/snapshot.py`, который:

- удаляет динамику (`csrf_token`, `request_id`, timestamps, URL/id сегменты);
- нормализует пробелы и переносы;
- сохраняет только значимые текстовые блоки:
  - mode label и units basis,
  - реквизиты документа,
  - totals (`ex/vat/inc`, `Moms`, `ROT-avdrag`, `Att betala`),
  - terms block.

## Обновление snapshots (только вручную)

```bash
python scripts/update_doc_snapshots.py
```

Скрипт не должен запускаться в CI автоматически.

## Как читать diff при падении

При mismatch тест показывает unified diff (первые N строк):

- `-` — строка из snapshot,
- `+` — текущий рендер,
- `@@` — контекстный ханк.

Оценивайте изменения осознанно:

1. Если поменялся шаблон/формулы намеренно — обновите snapshots вручную.
2. Если изменение не планировалось — это регрессия, исправьте код.

## CI

Тесты snapshot/smoke являются обычными `pytest` тестами и запускаются в стандартном test job.
