# Help / Tooltip registry

Единый источник подсказок: `app/help/registry.py`.

## Как добавить новую подсказку
1. Добавьте ключ в `HELP_TEXT` (формат: `domain.field`).
2. Обязательно заполните `ru`: `title`, `body`, `example`.
3. Желательно добавить `sv` для инвойсов/юридических тем.
4. В шаблоне используйте только ключ: `{{ help_icon("domain.field") }}`.
5. Не пишите текст help прямо в шаблоне.

## Структура записи
```python
"pricing.fixed_total_price": {
  "ru": {
    "title": "...",
    "body": "...",
    "example": "...",
    "link": "docs/PRICING.md",
  }
}
```

## Полезные ссылки
- Ценообразование: `docs/PRICING.md`
- Буферы: `docs/BUFFERS.md`
- VAT/ROT: `docs/VAT_ROT.md`
