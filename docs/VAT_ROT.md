# VAT / ROT (v1)

## Что считаем

В v1 сумма инвойса считается по snapshot-строкам `invoice_lines`:

- `Arbete exkl. moms` = сумма `line_total_ex_vat` для `kind=LABOR`
- `Material exkl. moms` = сумма `line_total_ex_vat` для `kind=MATERIAL`
- `Moms` = сумма `vat_amount` по всем строкам
- `Att betala` = `total_inc_vat - ROT-avdrag` (не ниже 0)

ROT в v1:

- применяется только к `LABOR`
- `eligible_labor_ex_vat = labour_ex_vat`
- `rot_amount = eligible_labor_ex_vat * rot_pct / 100`

## Snapshot при issue

При финализации (`ISSUED`) фиксируются:

- `rot_snapshot_enabled`
- `rot_snapshot_pct`
- `rot_snapshot_eligible_labor_ex_vat`
- `rot_snapshot_amount`

После issue перерасчёт использует snapshot, поэтому суммы не дрейфуют.

## Ограничения v1

- Нет отправки ROT-заявки в Skatteverket.
- Нет Peppol/Fortnox интеграции.
- Нет специальных кейсов reverse charge VAT.

## Поля на будущее

В `rot_cases` уже есть поля для расширения интеграции:

- `customer_personnummer`
- `property_identifier`
- `notes`


## Invoice consistency note
ROT affects payable total (`Att betala`) only. It must not change `subtotal_ex_vat` or scenario `price_ex_vat`.
