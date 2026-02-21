# Pricing v1

Экран: `/projects/{id}/pricing`.

## Что появилось в v1 engine

На экране теперь всегда считается **сравнение всех 5 режимов параллельно** на одном baseline:

- `HOURLY`
- `FIXED_TOTAL`
- `PER_M2`
- `PER_ROOM`
- `PIECEWORK`

Baseline (`compute_project_baseline`) — единый источник истины:

- `labor_hours_total`
- `labor_cost_internal`
- `materials_cost_internal` (если включено)
- `travel_setup_cost_internal` (если включено)
- `overhead_cost_internal`
- `internal_total_cost`
- единицы для продажи: `total_m2`, `rooms_count`, `items_count`

Все суммы считаются через `Decimal`, без float.

## Таблица сравнения

В блоке **«Сравнение режимов»** для каждого режима показываются:

- `Price ex VAT`
- `VAT`
- `Total inc VAT`
- `Effective hourly (ex VAT)`
- `Profit`
- `Margin %`
- `Warnings`

Поведение:

- выбранный режим подсвечивается;
- невалидные сценарии (например, `PER_M2` при `total_m2 = 0`) серые + warning;
- для `admin/operator` доступна кнопка `Use this mode`.

## Details (прозрачная математика)

У каждого сценария есть `Details`:

- формула расчёта в несколько строк;
- baseline breakdown (часы/себестоимость/материалы/накладные).

## VAT источник

VAT берётся из `settings.moms_percent` (fallback `25.00`), а не хардкодится в формулах.

## RBAC / CSRF / Audit

- Читать может любой авторизованный пользователь.
- Изменять pricing и выбирать режим могут только `admin`/`operator`.
- Все `POST` под CSRF.
- Аудит:
  - `pricing_updated`
  - `pricing_mode_selected`
  - `pricing_scenarios_viewed` (view-событие)
