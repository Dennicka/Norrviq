from __future__ import annotations

from jinja2 import pass_context
from markupsafe import Markup, escape

from .registry import get_help_entry


@pass_context
def help_icon(context, key: str) -> Markup:
    lang = context.get("lang", "ru")
    entry = get_help_entry(key, lang)
    labels = {
        "ru": {"more": "Подробнее", "help": "Подсказка"},
        "sv": {"more": "Läs mer", "help": "Hjälp"},
        "en": {"more": "Learn more", "help": "Help"},
    }
    lang_labels = labels.get(lang, labels["en"])
    if not entry:
        return Markup(f'<span class="help help-missing" title="Missing help: {escape(key)}" aria-label="{lang_labels["help"]}">?</span>')

    title = escape(entry.get("title", ""))
    body = escape(entry.get("body", ""))
    example = escape(entry.get("example", ""))
    link = escape(entry.get("link", "")) if entry.get("link") else ""

    link_html = Markup("")
    if link:
        link_html = Markup(f'<a href="{link}" class="help-popover-link">{lang_labels["more"]}</a>')

    return Markup(
        "<details class=\"help-popover\">"
        f"<summary class=\"help\" aria-label=\"{lang_labels['help']}\" title=\"{lang_labels['help']}\">?</summary>"
        f"<div class=\"help-popover-card\"><strong>{title}</strong><p>{body}</p><p><em>{example}</em></p>{link_html}</div>"
        "</details>"
    )
