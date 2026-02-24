# ESTIMATOR_ENGINE

`app/services/estimator_engine.py` содержит единый вход `build_project_estimate(db, project_id)`.

## Откуда берутся цифры

- Геометрия и объёмы: из комнат проекта (`rooms`) через `compute_room_geometry_from_model`.
- Часы по строкам: приоритет `project_work_items.calculated_hours`; если нет, берётся норма `work_types.hours_per_unit` и расчёт от объёма.
- Себестоимость труда: `estimated_hours * hourly_cost`, где ставка берётся из pricing override или настроек компании.
- Материалы: суммируются как `project_work_items.materials_cost_sek`.
- Сценарии pricing (`hourly`, `per_sqm`, `per_room`, `piecework`, `fixed_price`): строятся в одном ответе движка.

## Что нужно заполнить для корректного расчёта

- Комнаты с геометрией (площадь/периметр/высота) для m² и perimeter-базисов.
- Work item с типом работ и количеством/нормой.
- Pricing-параметры проекта (ставки по режимам), если нужен расчёт revenue.

## Почему сценарий может блокироваться

Сценарий возвращается с `enabled=false`, если не хватает входных данных. Причины попадают в `missing_requirements`, например:

- `MISSING_UNITS_M2`
- `MISSING_UNITS_ROOMS`
- `MISSING_PERIMETER_HEIGHT`
- `WARNING_MISSING_ITEMS`

Все предупреждения доступны в `warnings` ответа движка и не выбрасываются как exception.
