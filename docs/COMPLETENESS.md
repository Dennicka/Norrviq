# Completeness / Confidence

Completeness — это оценка достаточности данных проекта для выбранного pricing mode.

## Как считается score

- Источник правил: таблица `completeness_rules`.
- Для проекта выбираются активные правила по `segment` (`ANY` + сегмент клиента) и `pricing_mode` (`ANY` + выбранный mode).
- Каждое правило проверяется как pass/fail.
- `score = (sum(weight passed) / sum(weight active)) * 100`.
- Если весов нет, score = 100.

## Уровни

- `LOW`: < 50
- `MEDIUM`: 50–79
- `HIGH`: 80+

## Guardrails

Перед finalize Offer/Invoice дополнительно к sanity/floor выполняется completeness-check:

- Для `FIXED_TOTAL`, `PER_M2`, `PER_ROOM`:
  - если есть missing с `severity=BLOCK` → finalize блокируется (409)
  - если score ниже policy-threshold для режима → finalize блокируется (409)
- Ответ включает top-3 причины и ссылки на Project/Rooms/Pricing.

## Политика

В `pricing_policy`:

- `min_completeness_score_for_fixed` (default 70)
- `min_completeness_score_for_per_m2` (default 60)
- `min_completeness_score_for_per_room` (default 60)
- `warn_only_below_score` (default false)
