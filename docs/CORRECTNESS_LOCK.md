# Correctness Lock

Этот документ описывает регрессионный lock для коммерческих расчётов и issued-документов.

## Что гарантируют тесты

- Golden regression в `tests/regression/test_golden_regression.py` проверяет baseline/scenarios/offer/invoice и consistency gate по всем pricing modes: `HOURLY`, `FIXED_TOTAL`, `PER_M2`, `PER_ROOM`, `PIECEWORK`.
- Негативные тесты consistency gate подтверждают, что при рассинхроне возврат строго `409`.
- HTML snapshot suite фиксирует issued rendering для режимов fixed/per_m2/per_room/piecework.
- PDF smoke suite проверяет issued номера, totals и ключевые блоки (`Moms`, `ROT-avdrag`).

## Как осознанно обновлять golden/snapshots

1. Обновить goldens:

```bash
python scripts/update_golden.py
```

2. Обновить HTML snapshots:

```bash
python scripts/update_doc_snapshots.py
```

3. Проверить diff вручную: должны измениться только ожидаемые цифры/лейблы.
4. Прогнать `make check` перед коммитом.

## Что делать при mismatch 409

- Для offer/invoice finalize: проверить, что draft/lines соответствуют текущему pricing mode и ставкам.
- Если mismatch ожидаем (сознательное изменение бизнес-логики):
  - обновить golden/snapshots;
  - зафиксировать причину в PR.
- Нельзя отключать consistency gate или ослаблять сравнение денег до float.
