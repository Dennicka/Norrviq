# Pricing Policy (Margin Floor)

## Что проверяется
Для каждого pricing-сценария проверяется floor-политика:
- минимальная маржа `%`;
- минимум прибыли в SEK;
- минимум эффективной часовой ставки без НДС.

Если сценарий ниже floor, возвращаются причины:
- `MARGIN_BELOW_MIN`
- `PROFIT_BELOW_MIN`
- `EFFECTIVE_HOURLY_BELOW_MIN`
- `NEGATIVE_PROFIT`

## Что блокируется
Перед `Finalize/Issue` для Offer и Invoice система проверяет активный pricing mode проекта.

По умолчанию (`block_issue_below_floor=true`, `warn_only_mode=false`) выпуск блокируется, а API возвращает `409 Conflict`.

Если включен `warn_only_mode`, выпуск разрешается, но пишутся audit/log warning-события.

## Recommended minimum
Рекомендуемая минимальная цена `recommended_min_price_ex_vat` берётся как максимум из ограничений:

- `price >= internal_total_cost + min_profit`
- `price >= internal_total_cost / (1 - min_margin_pct/100)`
- `price >= min_hourly * labor_hours_total`

Также рассчитываются implied ставки:
- per m²
- per room
- per piece
- fixed total
