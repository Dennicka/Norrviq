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

## Конвертер ставок (T18)

На странице pricing добавлен блок **«Конвертер»**:

- ввод `Desired effective hourly (ex VAT)`;
- ввод `Target margin %`;
- кнопка `Calculate`.

Результат показывает:

- `Suggested fixed total`;
- `Suggested rate per m² / per room / per piece` (если есть соответствующие units);
- `Effective hourly`, `Profit`, `Margin %`;
- warnings при невозможности расчёта.

### Формулы конвертера

- `effective_hourly = price_ex_vat / labor_hours_total`
- `price_ex_vat_from_effective_hourly = desired_effective_hourly * labor_hours_total`
- `rate_per_m2 = price_ex_vat / total_m2` (если `total_m2 > 0`)
- `rate_per_room = price_ex_vat / rooms_count` (если `rooms_count > 0`)
- `rate_per_piece = price_ex_vat / items_count` (если `items_count > 0`)
- `fixed_total = price_ex_vat`
- `price_ex_vat_needed_for_margin = internal_total_cost / (1 - target_margin_pct/100)`

Ограничения:

- `target_margin_pct >= 100` — invalid (`INVALID_TARGET_MARGIN`);
- `labor_hours_total = 0` — warning `MISSING_BASELINE`;
- если `m²/rooms/items = 0`, соответствующие ставки не предлагаются и показываются warnings.

Округления:

- деньги/ставки — 2 знака;
- margin — 1 знак.

### Apply-кнопки

В конвертере доступны:

- `Apply to Fixed`
- `Apply to m²`
- `Apply to Room`
- `Apply to Piecework`

Нажатие записывает значение в `ProjectPricing` и сохраняет POST с CSRF.

RBAC:

- `viewer` может смотреть конвертер и считать результат;
- `admin/operator` могут выполнять `Apply`.

Audit события:

- `pricing_conversion_calculated`
- `pricing_conversion_applied` (в details: `mode`, `value`)
