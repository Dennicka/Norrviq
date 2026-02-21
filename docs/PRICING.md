# Pricing v1

Экран: `/projects/{id}/pricing`.

## Режимы

- `HOURLY` — базовая модель по часам, можно указать `hourly_rate_override`.
- `FIXED_TOTAL` — фикс на весь проект (`fixed_total_price`).
- `PER_M2` — цена за квадратный метр (`rate_per_m2`).
- `PER_ROOM` — цена за комнату (`rate_per_room`).
- `PIECEWORK` — сдельная ставка за единицу (`rate_per_piece`) + целевая маржа (`target_margin_pct`).

## Что сохраняется

Для каждого проекта хранится ровно одна запись `project_pricing`:

- выбранный `mode`;
- все параметрические поля (nullable);
- `include_materials`, `include_travel_setup_buffers`;
- `currency` (по умолчанию `SEK`).

При переключении режима значения в других полях не сбрасываются.

## Валидация v1

- Любая заполненная цена/ставка должна быть `> 0`.
- `target_margin_pct`: диапазон `0..80`.
- Обязательные поля по режиму:
  - `FIXED_TOTAL` -> `fixed_total_price`
  - `PER_M2` -> `rate_per_m2`
  - `PER_ROOM` -> `rate_per_room`
  - `PIECEWORK` -> `rate_per_piece`

## RBAC + CSRF

- Читать может любой авторизованный пользователь.
- Сохранять могут только `admin` и `operator`.
- `POST` защищён CSRF.
