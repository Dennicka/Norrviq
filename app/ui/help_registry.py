from __future__ import annotations

from typing import Final

HELP_TEXT: Final[dict[str, dict[str, str]]] = {
    "takeoff.include_openings_subtraction": {
        "ru": "Вычитать окна/двери из площади. Включайте для точного расхода, отключайте для грубого резерва.",
        "sv": "Subtrahera fönster/dörrar från ytan. Aktivera för exakt åtgång, stäng av för grov buffert.",
        "en": "Subtract windows/doors from area. Enable for accurate quantities, disable for rough safety buffer.",
    },
    "takeoff.paintable_basis": {
        "ru": "База покраски определяет, что идёт в расчёт: стены, потолок или сумма paintable total.",
        "sv": "Målningsbasen styr vad som räknas: väggar, tak eller totalt målningsbar yta.",
        "en": "Paintable basis controls what is used for calculations: walls, ceiling, or total paintable area.",
    },
    "pricing.modes": {
        "ru": "Режим цены меняет формулу расчёта: почасовой, фикс, за м², за комнату или за позицию.",
        "sv": "Prisläge ändrar beräkningsformeln: timpris, fastpris, per m², per rum eller per styck.",
        "en": "Pricing mode changes the calculation formula: hourly, fixed total, per m², per room, or piecework.",
    },
    "pricing.apply_best_mode": {
        "ru": "Применяет самый выгодный режим по текущей метрике. Проверьте предупреждения до сохранения.",
        "sv": "Väljer bästa läge enligt aktuell metrisk. Kontrollera varningar innan du sparar.",
        "en": "Applies the best mode for the current metric. Review warnings before saving.",
    },
    "pricing.floor_min_effective_hourly": {
        "ru": "Минимальная эффективная ставка в час. Помечает сценарии ниже порога как рискованные.",
        "sv": "Lägsta effektiv timintäkt. Markerar scenarier under gränsen som riskabla.",
        "en": "Minimum effective hourly sell rate. Flags scenarios below the floor as risky.",
    },
    "pricing.margin_profit_explained": {
        "ru": "Прибыль = выручка − полная себестоимость. Маржа = прибыль / выручка; при низкой марже растёт риск.",
        "sv": "Vinst = intäkt − total kostnad. Marginal = vinst / intäkt; låg marginal innebär högre risk.",
        "en": "Profit = revenue minus full cost. Margin = profit / revenue; low margin increases risk.",
    },
    "materials.waste_percent": {
        "ru": "Процент отходов добавляется к норме расхода. Используйте выше значение для сложной геометрии.",
        "sv": "Spillprocent läggs ovanpå normförbrukningen. Använd högre värde vid komplex geometri.",
        "en": "Waste percent is added on top of base consumption. Use higher values for complex geometry.",
    },
    "procurement.rounding_mode": {
        "ru": "Округление закупки: вверх до упаковки/кратно/минимуму. Влияет на остатки и бюджет.",
        "sv": "Avrundningsläge för inköp: upp till förpackning/multipel/minimum. Påverkar rest och budget.",
        "en": "Procurement rounding mode: round up to pack, multiple, or minimum. Affects leftovers and budget.",
    },
    "procurement.min_packs": {
        "ru": "Минимум упаковок на позицию. Полезно при требованиях поставщика или минимальном заказе.",
        "sv": "Minsta antal förpackningar per rad. Används vid leverantörskrav eller minsta order.",
        "en": "Minimum packs per line item. Useful for supplier constraints and minimum order rules.",
    },
    "procurement.pack_multiple": {
        "ru": "Заказ кратно N упаковкам (например, под паллету).",
        "sv": "Beställ i multiplar av N förpackningar (t.ex. pallregel).",
        "en": "Order in multiples of N packs (for example pallet constraints).",
    },
    "procurement.unit_mismatch_warning": {
        "ru": "Предупреждение о несовпадении единиц (норма vs упаковка). Проверьте конвертацию перед закупкой.",
        "sv": "Varning för enhetsmismatch (norm vs förpackning). Kontrollera konvertering före inköp.",
        "en": "Unit mismatch warning (consumption unit vs pack unit). Validate conversion before purchasing.",
    },
    "documents.issue_freeze_explained": {
        "ru": "После issue документ фиксируется: номер и расчётный снимок сохраняются для аудита.",
        "sv": "Efter utfärdande låses dokumentet: nummer och beräkningssnapshot sparas för revision.",
        "en": "Issuing freezes the document: number and calculation snapshot are stored for audit.",
    },
    "documents.print_vs_pdf": {
        "ru": "Print показывает версию в браузере. PDF экспортирует файл для отправки и архива.",
        "sv": "Print visar versionen i webbläsaren. PDF exporterar fil för utskick och arkiv.",
        "en": "Print opens browser view. PDF exports a file suitable for sharing and archiving.",
    },
}


_ALLOWED_LANGS = {"ru", "sv", "en"}


def _normalize_lang(lang: str | None) -> str:
    normalized = (lang or "").strip().lower()
    if normalized in _ALLOWED_LANGS:
        return normalized
    if normalized.startswith("sv"):
        return "sv"
    if normalized.startswith("en"):
        return "en"
    if normalized.startswith("ru"):
        return "ru"
    return "sv"


def get_help(key: str, lang: str) -> str:
    text = HELP_TEXT.get(key)
    if not text:
        return ""

    requested = _normalize_lang(lang)
    for candidate in (requested, "sv", "en", "ru"):
        value = text.get(candidate, "").strip()
        if value:
            return value
    return ""
