from __future__ import annotations

from typing import Final

HELP_TEXT: Final[dict[str, dict[str, dict[str, str]]]] = {
    "pricing.mode": {
        "ru": {"title": "Режим цены", "body": "Режим определяет, как считаем цену: по часам, фикс, за м², за комнату или за штуку.", "example": "Пример: для простого заказа выбираем HOURLY, для тендера — FIXED_TOTAL.", "link": "docs/PRICING.md"},
        "sv": {"title": "Prisläge", "body": "Läget styr hur priset räknas: timme, fastpris, per m², per rum eller per styck.", "example": "Exempel: HOURLY för löpande jobb, FIXED_TOTAL för upphandlat jobb."},
        "en": {"title": "Pricing mode", "body": "Mode controls how the sell price is calculated.", "example": "Example: HOURLY for open scope, FIXED_TOTAL for agreed scope."},
    },
    "pricing.hourly_rate_override": {"ru": {"title": "Ставка в час (override)", "body": "Если заполнить, система возьмёт эту ставку вместо стандартной. Пусто = берём дефолт из настроек.", "example": "Пример: 650 SEK/ч для срочного проекта."}, "sv": {"title": "Timpris (override)", "body": "Om fältet fylls används detta pris istället för standard.", "example": "Exempel: 650 SEK/h för akut uppdrag."}},
    "pricing.fixed_total_price": {"ru": {"title": "Фикс за весь проект", "body": "Клиент платит одну сумму за весь объём работ. Риски перерасхода времени на вашей стороне.", "example": "Пример: 120000 SEK за весь ремонт.", "link": "docs/PRICING.md"}, "sv": {"title": "Fast totalpris", "body": "Kunden betalar en fast summa för hela uppdraget.", "example": "Exempel: 120000 SEK totalt."}},
    "pricing.rate_per_m2": {"ru": {"title": "Ставка за м²", "body": "Цена умножается на площадь. Нужны корректные m² по комнатам.", "example": "Пример: 350 SEK/м² × 80 м² = 28000 SEK."}},
    "pricing.rate_per_room": {"ru": {"title": "Ставка за комнату", "body": "Цена считается по количеству комнат. Удобно, если площадь неизвестна.", "example": "Пример: 4000 SEK × 5 комнат = 20000 SEK."}},
    "pricing.rate_per_piece": {"ru": {"title": "Ставка за штуку", "body": "Цена по количеству однотипных единиц: окон, дверей, секций и т.д.", "example": "Пример: 900 SEK × 12 окон = 10800 SEK."}},
    "pricing.target_margin_pct": {"ru": {"title": "Целевая маржа", "body": "Желаемый процент прибыли от цены продажи. Нужен для подбора цены в piecework.", "example": "Пример: 25% значит из 10000 SEK хотим ~2500 SEK прибыли."}},
    "pricing.effective_hourly": {"ru": {"title": "Эффективная ставка в час", "body": "Показывает, сколько реально выходит SEK/ч после всех расчётов выбранного режима.", "example": "Пример: фикс 30000 SEK при 50 ч даёт 600 SEK/ч."}},
    "pricing.floor_policy": {"ru": {"title": "Нижний порог (floor policy)", "body": "Защита от слишком низкой цены. Сравнивает сценарий с минимумом по марже, прибыли и ставке в час.", "example": "Пример: если минимум 500 SEK/ч, сценарий с 430 SEK/ч будет flagged."}},
    "buffers.setup": {"ru": {"title": "Setup buffer", "body": "Время на подготовку: разгрузка, накрытие, раскладка инструмента.", "example": "Пример: +1.5 ч на запуск объекта."}, "sv": {"title": "Setup-buffert", "body": "Tid för förberedelser före arbete.", "example": "Exempel: +1,5 h."}},
    "buffers.cleanup": {"ru": {"title": "Cleanup buffer", "body": "Время на уборку после работ: вынос мусора, базовая очистка.", "example": "Пример: +1 ч после завершения."}},
    "buffers.travel": {"ru": {"title": "Travel buffer", "body": "Время и/или деньги на дорогу и логистику между объектами.", "example": "Пример: +0.75 ч и +250 SEK."}},
    "buffers.risk": {"ru": {"title": "Risk buffer", "body": "Запас на неопределённость: скрытые дефекты, задержки, доп.согласования.", "example": "Пример: +10% к трудозатратам."}},
    "buffers.basis": {"ru": {"title": "База буфера", "body": "К чему применяем правило: к часам или к стоимости. Это влияет на итог по-разному.", "example": "Пример: 10% от часов при 40 ч = +4 ч."}},
    "buffers.percent_vs_fixed": {"ru": {"title": "Процент vs фикс", "body": "Буфер может быть процентом, фиксированными часами или фиксированной суммой SEK.", "example": "Пример: либо +8%, либо +2 ч, либо +1200 SEK."}, "sv": {"title": "Procent vs fast", "body": "Buffert kan vara procent, fasta timmar eller fast SEK.", "example": "Exempel: +8%, +2 h eller +1200 SEK."}},
    "speed.multiplier": {"ru": {"title": "Множитель скорости", "body": ">1.0 замедляет (больше часов), <1.0 ускоряет (меньше часов).", "example": "Пример: 1.20 увеличит 50 ч до 60 ч.", "link": "docs/SPEED_PROFILES.md"}, "sv": {"title": "Hastighetsmultiplikator", "body": ">1.0 ger fler timmar, <1.0 färre timmar.", "example": "Exempel: 1,20 på 50 h blir 60 h."}},
    "speed.slow": {"ru": {"title": "Профиль SLOW", "body": "Для сложных условий: старый фонд, теснота, много ручной работы.", "example": "Пример: SLOW 1.20 для сложной реставрации."}},
    "speed.medium": {"ru": {"title": "Профиль MEDIUM", "body": "Базовый режим без сильных ускорений и замедлений.", "example": "Пример: MEDIUM 1.00 для обычной квартиры."}},
    "speed.fast": {"ru": {"title": "Профиль FAST", "body": "Для типовых задач и хорошо подготовленного объекта.", "example": "Пример: FAST 0.85, если фронт работ чистый и повторяемый."}},
    "quality.warning_vs_block": {"ru": {"title": "WARNING и BLOCK", "body": "WARNING показывает риск, но разрешает продолжать. BLOCK останавливает критичную операцию до исправления данных.", "example": "Пример: нулевая площадь может быть BLOCK для режима per m².", "link": "docs/DATA_QUALITY.md"}},
    "quality.anomalies": {"ru": {"title": "Аномалии данных", "body": "Это подозрительные значения: отрицательная цена, сверхбольшие часы, пустые обязательные поля.", "example": "Пример: 9999 ч на одну комнату — вероятная ошибка ввода."}},
    "completeness.score": {"ru": {"title": "Completeness score", "body": "Оценка полноты данных от 0 до 100. Чем выше, тем надёжнее расчёт цены и документов.", "example": "Пример: 82/100 = можно issue; 45/100 = нужно дозаполнить."}, "sv": {"title": "Completeness score", "body": "Poäng 0–100 som visar hur komplett underlaget är.", "example": "Exempel: 82/100 är bra."}},
    "completeness.fixed_block": {"ru": {"title": "Почему фикс блокируется", "body": "Фикс требует более точных данных. При низком score система блокирует issue, чтобы не продать в минус.", "example": "Пример: нет объёмов и трудозатрат — fixed недоступен."}},
    "invoice.lines": {"ru": {"title": "Строки инвойса", "body": "Каждая строка — отдельная позиция услуги или материала. Из строк складывается итог счета.", "example": "Пример: 1) Подготовка, 2) Окраска, 3) Материалы."}, "sv": {"title": "Fakturarader", "body": "Varje rad är en tjänst eller materialpost.", "example": "Exempel: förarbete, målning, material."}},
    "invoice.unit_price_ex_vat": {"ru": {"title": "Цена за единицу без НДС", "body": "Базовая цена позиции без moms. Итог строки = количество × цена за единицу.", "example": "Пример: 3 шт × 1200 SEK = 3600 SEK ex VAT."}},
    "invoice.moms": {"ru": {"title": "MOMS (VAT)", "body": "Шведский НДС, добавляется к сумме ex VAT по правилам ставки.", "example": "Пример: 10000 SEK ex VAT при 25% moms = 2500 SEK НДС.", "link": "docs/VAT_ROT.md"}, "sv": {"title": "MOMS", "body": "Mervärdesskatt som läggs på pris exkl. moms.", "example": "Exempel: 10000 SEK + 25% = 12500 SEK."}},
    "invoice.rot_pct": {"ru": {"title": "ROT-avdrag", "body": "Налоговый вычет в Швеции на трудовую часть. Уменьшает сумму к оплате клиентом.", "example": "Пример: труд 20000 SEK, ROT 30% → клиент платит на 6000 SEK меньше.", "link": "docs/VAT_ROT.md"}, "sv": {"title": "ROT-avdrag", "body": "Skattereduktion på arbetskostnad enligt svenska regler.", "example": "Exempel: 30% av arbetsdelen dras av."}},
    "invoice.issued_lock": {"ru": {"title": "Блокировка после issue", "body": "После выпуска документ фиксируется для аудита и закона. Нельзя менять ключевые поля задним числом.", "example": "Пример: status ISSUED — редактирование строк отключено."}, "sv": {"title": "Låsning efter issue", "body": "Efter utfärdande låses fakturan för spårbarhet.", "example": "Exempel: status ISSUED kan inte redigeras."}},
    "terms.versioning": {"ru": {"title": "Версионирование шаблонов", "body": "Правки условий создают новую версию, чтобы старые документы оставались неизменными.", "example": "Пример: v3 меняет штрафы, но договоры с v2 остаются как были."}, "sv": {"title": "Versionshantering", "body": "Ändringar skapar ny version så gamla dokument inte ändras retroaktivt.", "example": "Exempel: v3 ersätter v2 för nya avtal."}},
    "terms.snapshot_on_issue": {"ru": {"title": "Снимок условий при issue", "body": "При выпуске документа текст условий копируется в snapshot. Это защищает от споров после обновления шаблона.", "example": "Пример: даже если шаблон обновили, в инвойсе останется текст на момент issue."}},
    "pricing_policy.min_margin_pct": {"ru": {"title": "Минимальная маржа", "body": "Нижняя граница рентабельности. Если ниже — цена помечается как риск/ниже floor.", "example": "Пример: минимум 15% — сценарий с 9% считается слишком низким."}},
    "pricing_policy.min_profit_sek": {"ru": {"title": "Минимальная прибыль", "body": "Минимальная абсолютная прибыль в SEK, чтобы проект покрывал бизнес-расходы.", "example": "Пример: минимум 1500 SEK, иначе сценарий ниже floor."}},
    "pricing_policy.min_effective_hourly": {"ru": {"title": "Мин. эффективная ставка", "body": "Нижняя граница фактической ставки продажи на час после всех пересчётов.", "example": "Пример: минимум 500 SEK/ч, а сценарий даёт 430 SEK/ч."}},
    "buffers.include_setup_cleanup_travel": {"ru": {"title": "Включать setup/cleanup/travel", "body": "Если включено, в смету добавляются соответствующие буферы.", "example": "Пример: +2 ч setup/cleanup и +0.5 ч travel."}},
    "buffers.include_risk": {"ru": {"title": "Включать risk", "body": "Добавляет резерв на неопределённость в проекте.", "example": "Пример: +7% к базовым часам."}},
    "invoice.merge_strategy": {"ru": {"title": "Стратегия merge строк", "body": "Определяет, как обновлять строки при регенерации: объединять, заменять или добавлять.", "example": "Пример: replace удалит старые авто-строки и создаст новые."}},
    "invoice.apply_rot": {"ru": {"title": "Применить ROT", "body": "Включает расчёт ROT для подходящих трудовых строк.", "example": "Пример: галочка включена — итог клиента уменьшается."}},
    "invoice.status": {"ru": {"title": "Статус инвойса", "body": "Черновик, выпущен, оплачен и т.д. Статус управляет доступностью действий.", "example": "Пример: DRAFT можно править, ISSUED — почти нет."}},
    "quality.rule_severity": {"ru": {"title": "Серьёзность правила", "body": "Выберите, предупреждать или блокировать действие при нарушении правила.", "example": "Пример: отрицательная сумма = BLOCK, необычно большая сумма = WARNING."}},
}


def get_help_entry(key: str, lang: str) -> dict[str, str] | None:
    entry = HELP_TEXT.get(key)
    if not entry:
        return None
    if lang in entry:
        return entry[lang]
    return entry.get("ru")
