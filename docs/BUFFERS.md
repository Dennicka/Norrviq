# Buffers engine

## Что это
Буферы добавляют запас к baseline по времени и/или внутренней себестоимости:
- `SETUP`
- `CLEANUP`
- `TRAVEL`
- `RISK`

## Настройка
1. Админ открывает `/settings/buffers`.
2. Создает правила с:
   - `basis`: `LABOR_HOURS` или `INTERNAL_COST`
   - `unit`: `PERCENT`, `FIXED_HOURS`, `FIXED_SEK`
   - `scope`: `GLOBAL`, `PROJECT`, `WORKTYPE`, `CATEGORY`
3. Для проекта на `/projects/{id}/buffers` можно включать/выключать:
   - setup/cleanup/travel
   - risk

## Примеры
- Setup +0.5h на конкретный worktype: `kind=SETUP, basis=LABOR_HOURS, unit=FIXED_HOURS, value=0.50, scope=WORKTYPE`.
- Risk +10%: `kind=RISK, basis=INTERNAL_COST, unit=PERCENT, value=10.00, scope=GLOBAL`.

## Precedence
Применение правил в порядке:
1. `PROJECT`
2. `WORKTYPE`
3. `CATEGORY`
4. `GLOBAL`

Внутри kind+basis:
- фиксированные добавки сначала,
- процент от raw базы (`raw_labor_hours_total`/`raw_internal_cost`) независимо от порядка.

## Влияние на pricing
Pricing details показывает:
- raw baseline,
- breakdown буферов,
- итоговый baseline после буферов.

Это повышает прозрачность и не меняет результаты при отсутствии правил.
