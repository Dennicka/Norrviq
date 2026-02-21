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

### Правила отображения

- деньги всегда рендерятся с 2 знаками после запятой;
- effective hourly рендерится с 2 знаками;
- margin отображается с 1 знаком и суффиксом `%`;
- `NaN`/`Infinity`/`-0.00` в UI не показываются (заменяются на `—` или `0.00`).

### Warnings (коды и смысл)

Каждый warning имеет код, который удобно проверять в тестах и логике UI:

- `MISSING_UNITS_M2` — `total_m2 = 0`, расчёт per m² недоступен;
- `MISSING_UNITS_ROOMS` — `rooms_count = 0`, расчёт per room недоступен;
- `MISSING_ITEMS` — `items_count = 0`, piecework недоступен;
- `MISSING_BASELINE` — `labor_hours_total = 0`, effective hourly не рассчитывается;
- `NEGATIVE_MARGIN` — профит отрицательный;
- `LOW_MARGIN` — маржа ниже UI-порога (сейчас 10%).

Поведение:

- выбранный режим подсвечивается;
- сценарии с критическими warning (нет единиц продажи) помечаются как `Not applicable` и подсвечиваются как недоступные;
- в ячейке есть пояснение «Почему недоступно?» на русском;
- для `admin/operator` доступна кнопка `Use this mode`.

## Как выбирать режим

1. Заполните нужные ставки в форме (значения по режимам хранятся и не должны пропадать при переключении).
2. Используйте `Save` для сохранения всех параметров текущей формы.
3. Используйте `Use this mode` в строке сценария, чтобы быстро выбрать конкретный режим в `ProjectPricing.mode`.
4. При нажатии кнопки блокируются (`disabled`) и показывают `Saving...` для защиты от двойного клика.

## Details (прозрачная математика)

У каждого сценария есть `Details`:

- формула расчёта в несколько строк;
- baseline breakdown (часы/себестоимость/материалы/накладные);
- применённые include-флаги (`materials`, `travel/setup buffers`).

## Effective hourly

`Effective hourly (ex VAT)` — это фактическая ставка продажи за час:

- `price_ex_vat / labor_hours_total`, если базовые часы есть;
- если `labor_hours_total = 0`, значение недоступно и добавляется warning `MISSING_BASELINE`.

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
