# Golden Regression Suite (Estimator & Pricing)

## Что это

Golden-регрессия фиксирует эталонные результаты расчётов для набора проектов. Любой дрейф цифр (часы, себестоимость, pricing-сценарии, floor policy, converter) должен быть явным и осознанным.

Снимки хранятся в `tests/golden/*.json` и сравниваются в `tests/regression/test_golden_regression.py`.

## Состав кейсов

- `g1_small_room` — маленькая комната, минимальные материалы.
- `g2_apartment` — квартира (несколько комнат, больше работ и затрат).
- `g3_missing_units` — edge-case без площадей/комнат, но с часами.
- `g4_large` — увеличенный проект для мягкого perf-check в регрессии.

## Формат golden JSON

- Денежные значения и часы сохраняются как строки (`Decimal` → string), чтобы исключить float drift.
- JSON сериализуется со стабильным порядком ключей (`sort_keys=True`).
- В snapshot включены:
  - baseline totals,
  - pricing scenarios,
  - converter outputs,
  - floor policy evaluation,
  - compute timing (для large-case gate).

## Как читать diff

При расхождении тест печатает адрес ключа и тип изменения:

- `~ path.to.key` — значение изменилось,
- `+ path.to.key` — ключ появился,
- `- path.to.key` — ключ исчез.

Это позволяет быстро локализовать, где именно изменился алгоритм.

## Как обновлять golden (только вручную)

Только после осознанного изменения бизнес-логики:

```bash
python scripts/update_golden.py
pytest tests/regression/test_golden_regression.py
```

> В CI auto-update запрещён: `update_golden.py` **не** запускается автоматически.
