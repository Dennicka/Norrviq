from typing import Callable

TRANSLATIONS_RU = {
    "title.app": "Norrviq Måleri AB — система смет и аналитики",
    "menu.projects": "Проекты",
    "menu.finance": "Финансы",
    "menu.workers": "Сотрудники",
    "menu.settings": "Настройки",
    "menu.language": "Язык",
    "index.header": "Панель управления Norrviq Måleri AB",
    "index.lead": "Здесь будет система смет, учёта и аналитики.",
}

TRANSLATIONS_SV = {
    "title.app": "Norrviq Måleri AB — kalkyl- och analyssystem",
    "menu.projects": "Projekt",
    "menu.finance": "Ekonomi",
    "menu.workers": "Anställda",
    "menu.settings": "Inställningar",
    "menu.language": "Språk",
    "index.header": "Norrviq Måleri AB — kontrollpanel",
    "index.lead": "Här kommer systemet för kalkyler, uppföljning och analys.",
}


def get_translation(lang: str, key: str) -> str:
    translations = TRANSLATIONS_RU if lang == "ru" else TRANSLATIONS_SV
    return translations.get(key, key)


def make_t(lang: str) -> Callable[[str], str]:
    def t(key: str) -> str:
        return get_translation(lang, key)

    return t
