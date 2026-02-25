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
    "pricing_policy.block_issue_below_floor": {
        "ru": {"title": "Блокировать выпуск ниже floor", "body": "Если включено, нельзя выпустить оффер/инвойс при нарушении минимумов политики.", "example": "Пример: при марже ниже минимума кнопка выпуска блокируется."},
        "en": {"title": "Block issue below floor", "body": "When enabled, issuing Offer/Invoice is blocked if floor checks fail.", "example": "Example: too-low margin blocks issue."},
    },
    "pricing_policy.warn_only_mode": {
        "ru": {"title": "Только предупреждение", "body": "Режим без блокировки: система только предупреждает о нарушении порогов.", "example": "Пример: можно выпустить документ, но увидите warning."},
        "en": {"title": "Warning only mode", "body": "Do not block actions; show warnings only.", "example": "Example: issue is allowed but flagged."},
    },
    "pricing_policy.min_completeness_per_room": {
        "ru": {"title": "Минимальная полнота для per room", "body": "Минимальный score полноты, чтобы разрешить режим за комнату.", "example": "Пример: при score 45 и пороге 60 режим будет flagged."},
    },
    "buffer_rules.kind": {
        "ru": {"title": "Тип буфера", "body": "Определяет назначение правила: setup, cleanup, travel или risk.", "example": "Пример: TRAVEL добавляет резерв на логистику."},
    },
    "buffer_rules.scope": {
        "ru": {"title": "Scope", "body": "Где действует правило: глобально, для проекта, вида работ или категории.", "example": "Пример: WORKTYPE ограничивает правило конкретным кодом работ."},
    },
    "buffer_rules.priority": {
        "ru": {"title": "Приоритет", "body": "Порядок применения правил. Большее значение = выше приоритет.", "example": "Пример: специфичное правило ставят выше общего."},
    },
    "project_buffers.speed_profile": {
        "ru": {"title": "Профиль скорости", "body": "Множитель, который ускоряет или замедляет базовые трудозатраты проекта.", "example": "Пример: profile 1.15 добавит 15% часов."},
    },
    "paint_systems.order": {
        "ru": {"title": "Порядок", "body": "Позиция шага в цепочке системы окраски.", "example": "Пример: 1 = грунт, 2 = первый слой, 3 = финиш."},
    },
    "paint_systems.surface": {
        "ru": {"title": "Поверхность", "body": "Для какой поверхности применяется шаг рецепта.", "example": "Пример: WALL или CEILING."},
    },
    "paint_systems.recipe": {
        "ru": {"title": "Рецепт", "body": "Какой material recipe использовать в этом шаге.", "example": "Пример: грунт + краска бренда X."},
    },
    "paint_systems.override_coats": {
        "ru": {"title": "Переопределить слои", "body": "Локально заменить число слоёв для шага, не меняя рецепт в целом.", "example": "Пример: вместо 2 слоёв задать 3."},
    },
    "paint_systems.override_waste": {
        "ru": {"title": "Переопределить отходы %", "body": "Локально заменить процент отходов для шага.", "example": "Пример: 8% вместо стандартных 5%."},
    },
    "paint_systems.optional": {
        "ru": {"title": "Опционально", "body": "Шаг можно пропустить, если он не нужен для конкретного проекта.", "example": "Пример: дополнительный защитный слой как optional."},
    },
    "materials_norms.basis_type": {
        "ru": {"title": "Тип базы", "body": "Какая геометрия используется как основание нормы (пол, стены, периметр и т.д.).", "example": "Пример: wall_area для расхода по стенам."},
    },
    "materials_norms.consumption_qty": {
        "ru": {"title": "Расход", "body": "Количество материала на базовую величину.", "example": "Пример: 0.12 л на 1 м²."},
    },
    "materials_norms.per_basis_qty": {
        "ru": {"title": "На базовое количество", "body": "Базовое количество, к которому привязан расход.", "example": "Пример: 10 м², если расход задан на 10 м²."},
    },
    "materials_norms.layers_multiplier": {
        "ru": {"title": "Множитель слоёв", "body": "Учитывает число слоёв при итоговом расходе материала.", "example": "Пример: 2 слоя = расход ×2."},
    },
    "materials_norms.work_type_code": {
        "ru": {"title": "Код типа работ", "body": "Внутренний код работ для привязки нормы. Код не переводится и хранится как есть.", "example": "Пример: PAINT_WALL_INTERIOR."},
    },
    "materials_norms.material_unit": {
        "ru": {"title": "Единица материала", "body": "Единица измерения расхода материала.", "example": "Пример: l, kg, pcs."},
    },
    "materials_norms.waste_percent": {
        "ru": {"title": "Отходы %", "body": "Дополнительный запас на потери/остатки.", "example": "Пример: 7% повышает итоговый расход на 1.07."},
    },
    "terms_templates.segment": {
        "ru": {"title": "Сегмент", "body": "Бизнес-сегмент шаблона условий.", "example": "Пример: B2C или B2B."},
    },
    "terms_templates.doc_type": {
        "ru": {"title": "Тип документа", "body": "Для какого документа применяется шаблон.", "example": "Пример: OFFER или INVOICE."},
    },
    "terms_templates.language": {
        "ru": {"title": "Язык", "body": "Язык текста шаблона условий.", "example": "Пример: ru/sv/en."},
    },
    "terms_templates.version_from_template": {
        "ru": {"title": "Версия из шаблона", "body": "Создать новую версию, скопировав существующий шаблон.", "example": "Пример: взять v2 как основу для v3."},
    },
    "terms_templates.active": {
        "ru": {"title": "Активный", "body": "Активная версия доступна для новых документов.", "example": "Пример: выключите старую версию после публикации новой."},
    },
}


def get_help_entry(key: str, lang: str) -> dict[str, str] | None:
    entry = HELP_TEXT.get(key)
    if not entry:
        return None
    if lang in entry:
        return entry[lang]
    return entry.get("ru")

HELP_TEXT.update({
    "pricing_policy.min_margin_pct": {
        "ru": {"title": "Минимальная маржа %", "body": "Нижний порог маржи для сценария цены.", "example": "Если маржа ниже порога, система покажет предупреждение/блок."},
        "sv": {"title": "Minsta marginal %", "body": "Lägsta tillåtna marginal för prisscenario.", "example": "Under tröskeln visas varning/blockering."},
        "en": {"title": "Minimum margin %", "body": "Lowest allowed margin for a pricing scenario.", "example": "Below threshold the system warns or blocks issue."},
    },
    "pricing_policy.min_profit_sek": {
        "ru": {"title": "Минимальная прибыль (SEK)", "body": "Абсолютный минимум прибыли по документу.", "example": "Если прибыль ниже порога, правило floor срабатывает."},
        "sv": {"title": "Minsta vinst (SEK)", "body": "Absolut minimivinst per dokument.", "example": "Under nivån triggas floor-regeln."},
        "en": {"title": "Minimum profit (SEK)", "body": "Absolute minimum profit per document.", "example": "If lower than threshold, floor policy is triggered."},
    },
    "pricing_policy.min_effective_hourly": {
        "ru": {"title": "Минимальная эффективная ставка", "body": "Минимум SEK/ч после всех расчётов.", "example": "Защищает от слишком дешёвых фиксированных цен."},
        "sv": {"title": "Minsta effektiv timtaxa", "body": "Lägsta SEK/h efter alla beräkningar.", "example": "Skyddar mot för låg fastprisnivå."},
        "en": {"title": "Minimum effective hourly", "body": "Minimum SEK/hour after all calculations.", "example": "Prevents underpriced fixed totals."},
    },
    "pricing_policy.warn_only_mode": {
        "ru": {"title": "Только предупреждение", "body": "Вместо блокировки показывает предупреждение.", "example": "Используйте при мягком контроле в пилоте."},
        "sv": {"title": "Endast varning", "body": "Visar varning i stället för blockering.", "example": "Används vid mjuk kontroll under pilot."},
        "en": {"title": "Warning only", "body": "Shows warnings instead of blocking.", "example": "Useful during rollout when control is soft."},
    },
    "pricing_policy.warn_only_below_score": {
        "ru": {"title": "Порог полноты: только предупреждение", "body": "Ниже порога полноты система предупреждает, но не блокирует.", "example": "Подходит для переходного периода."},
        "sv": {"title": "Fullständighet: endast varning", "body": "Under tröskeln visas varning men ingen blockering.", "example": "Bra under övergångsperiod."},
        "en": {"title": "Completeness: warning only", "body": "Below threshold system warns but does not block.", "example": "Useful for transition periods."},
    },
    "completeness.fixed_block": {
        "ru": {"title": "Порог полноты (fixed)", "body": "Минимальный score полноты для fixed режима.", "example": "Ниже порога fixed-прайс помечается рисковым."},
        "sv": {"title": "Fullständighetströskel (fastpris)", "body": "Minsta score för fastprisläge.", "example": "Under nivån markeras fastpris som riskfyllt."},
        "en": {"title": "Completeness threshold (fixed)", "body": "Minimum completeness score for fixed mode.", "example": "Below threshold fixed pricing is treated as risky."},
    },
    "completeness.score": {
        "ru": {"title": "Порог полноты", "body": "Минимальный уровень заполненности данных для режима.", "example": "Чем ниже score, тем выше риск ошибки цены."},
        "sv": {"title": "Fullständighetspoäng", "body": "Miniminivå för datakomplettering i läget.", "example": "Låg poäng innebär högre prisrisk."},
        "en": {"title": "Completeness score", "body": "Minimum data completeness level for the mode.", "example": "Lower score means higher pricing risk."},
    },
    "pricing_policy.min_completeness_per_room": {
        "ru": {"title": "Порог полноты для per room", "body": "Минимальный score для режима цены за комнату.", "example": "При низком score система предупредит/заблокирует."},
        "sv": {"title": "Tröskel för per room", "body": "Minsta score för pris per rum.", "example": "Låg score ger varning/blockering."},
        "en": {"title": "Threshold for per room", "body": "Minimum completeness score for per-room pricing.", "example": "Low score triggers warning/block."},
    },
    "buffer_rules.kind": {
        "ru": {"title": "Тип буфера", "body": "Какой вид буфера применяется к базе.", "example": "SETUP, CLEANUP, TRAVEL или RISK."},
        "sv": {"title": "Bufferttyp", "body": "Vilken buffertsort som läggs på basen.", "example": "SETUP, CLEANUP, TRAVEL eller RISK."},
        "en": {"title": "Buffer kind", "body": "Defines which buffer type is applied.", "example": "SETUP, CLEANUP, TRAVEL, or RISK."},
    },
    "buffers.basis": {
        "ru": {"title": "База", "body": "От чего считается буфер: часы или себестоимость.", "example": "LABOR_HOURS или INTERNAL_COST."},
        "sv": {"title": "Bas", "body": "Vad bufferten beräknas från: timmar eller kostnad.", "example": "LABOR_HOURS eller INTERNAL_COST."},
        "en": {"title": "Basis", "body": "What the buffer is calculated from: hours or cost.", "example": "LABOR_HOURS or INTERNAL_COST."},
    },
    "buffers.percent_vs_fixed": {
        "ru": {"title": "Единица буфера", "body": "Буфер может быть в процентах или фиксированным значением.", "example": "PERCENT, FIXED_HOURS, FIXED_SEK."},
        "sv": {"title": "Buffertenhet", "body": "Buffert kan vara procent eller fast värde.", "example": "PERCENT, FIXED_HOURS, FIXED_SEK."},
        "en": {"title": "Buffer unit", "body": "Buffer can be percent or fixed value.", "example": "PERCENT, FIXED_HOURS, FIXED_SEK."},
    },
    "buffer_rules.scope": {
        "ru": {"title": "Область применения", "body": "Где действует правило: глобально, проект или тип работ.", "example": "PROJECT + scope_id применяет правило к одному проекту."},
        "sv": {"title": "Omfattning", "body": "Var regeln gäller: globalt, projekt eller arbetstyp.", "example": "PROJECT + scope_id gäller ett projekt."},
        "en": {"title": "Scope", "body": "Where the rule applies: global, project, or work type.", "example": "PROJECT + scope_id applies to one project."},
    },
    "buffer_rules.priority": {
        "ru": {"title": "Приоритет", "body": "Чем выше, тем раньше правило рассматривается.", "example": "Сначала выбирается правило с максимальным приоритетом."},
        "sv": {"title": "Prioritet", "body": "Högre värde betyder högre prioritet.", "example": "Regeln med högst prioritet väljs först."},
        "en": {"title": "Priority", "body": "Higher number means the rule is considered first.", "example": "Highest-priority matching rule wins."},
    },
    "buffers.include_setup_cleanup_travel": {
        "ru": {"title": "Include setup/cleanup/travel", "body": "Включает соответствующие виды буферов в расчёт проекта.", "example": "Отключите, если такие затраты учтены отдельно."},
        "sv": {"title": "Inkludera setup/cleanup/travel", "body": "Tar med dessa bufferttyper i projektberäkningen.", "example": "Stäng av om de hanteras separat."},
        "en": {"title": "Include setup/cleanup/travel", "body": "Includes these buffer kinds in project calculations.", "example": "Disable if those costs are handled separately."},
    },
    "buffers.include_risk": {
        "ru": {"title": "Include risk", "body": "Добавляет риск-буфер в базовый расчёт.", "example": "Используйте для проектов с неопределённостью."},
        "sv": {"title": "Inkludera risk", "body": "Tar med riskbuffert i grundberäkningen.", "example": "Använd för osäkra projekt."},
        "en": {"title": "Include risk", "body": "Adds risk buffer into baseline calculation.", "example": "Use for projects with uncertainty."},
    },
    "project_buffers.speed_profile": {
        "ru": {"title": "Профиль скорости", "body": "Множитель производительности команды для этого проекта.", "example": "1.15 медленнее, 0.90 быстрее."},
        "sv": {"title": "Hastighetsprofil", "body": "Produktivitetsmultiplikator för projektet.", "example": "1.15 långsammare, 0.90 snabbare."},
        "en": {"title": "Speed profile", "body": "Team productivity multiplier for this project.", "example": "1.15 slower, 0.90 faster."},
    },
    "materials_norms.basis_type": {
        "ru": {"title": "Тип базы", "body": "Геометрическая база, относительно которой считается расход.", "example": "wall_area, ceiling_area, perimeter и т.д."},
        "sv": {"title": "Bastyp", "body": "Geometrisk bas som förbrukningen räknas mot.", "example": "wall_area, ceiling_area, perimeter m.fl."},
        "en": {"title": "Basis type", "body": "Geometry basis used for consumption calculation.", "example": "wall_area, ceiling_area, perimeter, etc."},
    },
    "materials_norms.consumption_qty": {
        "ru": {"title": "Расход", "body": "Количество материала на базовый объём.", "example": "0.3 л на 1 м²."},
        "sv": {"title": "Förbrukningsmängd", "body": "Materialmängd per basvolym.", "example": "0.3 l per 1 m²."},
        "en": {"title": "Consumption qty", "body": "Material quantity per basis volume.", "example": "0.3 L per 1 m²."},
    },
    "materials_norms.per_basis_qty": {
        "ru": {"title": "На базовое количество", "body": "Размер базы, к которому привязан расход.", "example": "Расход 3 л на 10 м² => per_basis_qty=10."},
        "sv": {"title": "Per basmängd", "body": "Basstorlek som förbrukningen avser.", "example": "3 l per 10 m² => per_basis_qty=10."},
        "en": {"title": "Per basis qty", "body": "Basis size that the consumption quantity refers to.", "example": "3 L per 10 m² => per_basis_qty=10."},
    },
    "materials_norms.per_basis_unit": {
        "ru": {"title": "Единица базы", "body": "Единица измерения для базового количества.", "example": "m2, rm, room."},
        "sv": {"title": "Basenhet", "body": "Enhet för basmängden.", "example": "m2, rm, room."},
        "en": {"title": "Per basis unit", "body": "Unit for the basis quantity.", "example": "m2, rm, room."},
    },
    "materials_norms.layers_multiplier": {
        "ru": {"title": "Множитель слоёв", "body": "Умножает расход на число слоёв в работах.", "example": "2 слоя => расход ×2."},
        "sv": {"title": "Lagermultiplikator", "body": "Multiplicerar förbrukning med antal lager.", "example": "2 lager => förbrukning ×2."},
        "en": {"title": "Layers multiplier", "body": "Multiplies consumption by number of coats/layers.", "example": "2 layers => consumption ×2."},
    },
    "materials_norms.waste_percent": {
        "ru": {"title": "Отходы %", "body": "Дополнительный процент на потери материала.", "example": "5% означает коэффициент 1.05."},
        "sv": {"title": "Spill %", "body": "Extra procent för materialspill.", "example": "5% betyder faktor 1.05."},
        "en": {"title": "Waste %", "body": "Extra percentage for material waste.", "example": "5% means factor 1.05."},
    },
    "materials_norms.work_type_code": {
        "ru": {"title": "Код типа работ", "body": "Связывает норму с конкретным типом работ.", "example": "paint_walls, paint_ceiling."},
        "sv": {"title": "Arbetstypkod", "body": "Kopplar normen till en arbetstyp.", "example": "paint_walls, paint_ceiling."},
        "en": {"title": "Work type code", "body": "Binds the norm to a specific work type.", "example": "paint_walls, paint_ceiling."},
    },
    "paint_systems.override_coats": {
        "ru": {"title": "Переопределить слои", "body": "Задаёт число слоёв для шага вместо значения из рецепта.", "example": "Укажите 2, чтобы принудительно красить в 2 слоя."},
        "sv": {"title": "Åsidosätt lager", "body": "Sätter antal lager för steget istället för receptvärdet.", "example": "Ange 2 för att alltid måla två lager."},
        "en": {"title": "Override coats", "body": "Sets coat count for the step instead of recipe default.", "example": "Set 2 to force two coats."},
    },
    "paint_systems.override_waste": {
        "ru": {"title": "Переопределить отходы %", "body": "Заменяет процент отходов рецепта для конкретного шага.", "example": "10% для сложной геометрии."},
        "sv": {"title": "Åsidosätt spill %", "body": "Ersätter receptets spillprocent för steget.", "example": "10% för komplex geometri."},
        "en": {"title": "Override waste %", "body": "Overrides recipe waste percentage for this step.", "example": "10% for complex geometry."},
    },
    "paint_systems.optional": {
        "ru": {"title": "Опционально", "body": "Шаг не обязателен и может быть пропущен без ошибки.", "example": "Например, грунт только при плохом основании."},
        "sv": {"title": "Valfri", "body": "Steget är inte obligatoriskt och kan hoppas över.", "example": "T.ex. primer bara vid dåligt underlag."},
        "en": {"title": "Optional", "body": "Step is not mandatory and may be skipped.", "example": "E.g., primer only for poor substrate."},
    },
    "paint_systems.versioning": {
        "ru": {"title": "Версионирование", "body": "Новые версии системы сохраняют историю изменений.", "example": "Активной обычно остаётся последняя версия."},
        "sv": {"title": "Versionering", "body": "Nya systemversioner behåller ändringshistorik.", "example": "Vanligtvis är senaste versionen aktiv."},
        "en": {"title": "Versioning", "body": "New system versions preserve change history.", "example": "Usually the latest version is active."},
    },
    "terms_templates.segment": {
        "ru": {"title": "Сегмент", "body": "Контекст использования шаблона условий.", "example": "b2b, b2c или internal."},
        "sv": {"title": "Segment", "body": "Kontext där villkorsmallen används.", "example": "b2b, b2c eller internal."},
        "en": {"title": "Segment", "body": "Context where the terms template is used.", "example": "b2b, b2c, or internal."},
    },
    "terms_templates.doc_type": {
        "ru": {"title": "Тип документа", "body": "Для какого документа применяются условия.", "example": "offer или invoice."},
        "sv": {"title": "Dokumenttyp", "body": "Vilken dokumenttyp villkoren gäller för.", "example": "offer eller invoice."},
        "en": {"title": "Doc type", "body": "Document type the terms apply to.", "example": "offer or invoice."},
    },
    "terms_templates.version_from_template": {
        "ru": {"title": "Версия из шаблона", "body": "Создаёт новую версию на основе существующей.", "example": "Выберите шаблон, чтобы переиспользовать текст."},
        "sv": {"title": "Version från mall", "body": "Skapar en ny version baserat på befintlig mall.", "example": "Välj mall för att återanvända text."},
        "en": {"title": "Version from template", "body": "Creates a new version based on an existing template.", "example": "Select template to reuse body text."},
    },
    "terms_templates.active": {
        "ru": {"title": "Активный", "body": "Активные шаблоны доступны для выбора по умолчанию.", "example": "Отключите старые версии, чтобы избежать путаницы."},
        "sv": {"title": "Aktiv", "body": "Aktiva mallar är tillgängliga som standardval.", "example": "Inaktivera gamla versioner för tydlighet."},
        "en": {"title": "Active", "body": "Active templates are available for default selection.", "example": "Disable old versions to avoid confusion."},
    },
    "terms.snapshot_on_issue": {
        "ru": {"title": "Сохранить как новую версию", "body": "Сохраняет изменения в отдельной версии, не ломая старые документы.", "example": "История версий нужна для аудита."},
        "sv": {"title": "Spara som ny version", "body": "Sparar ändringar i en ny version utan att påverka gamla dokument.", "example": "Versionshistorik behövs för revision."},
        "en": {"title": "Save as new version", "body": "Stores changes in a new version without breaking old documents.", "example": "Version history supports audits."},
    },
})
