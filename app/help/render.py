from __future__ import annotations

from jinja2 import pass_context
from markupsafe import Markup, escape

from .registry import get_help_entry


@pass_context
def help_icon(context, key: str) -> Markup:
    lang = context.get("lang", "ru")
    entry = get_help_entry(key, lang)
    if not entry:
        return Markup(f'<span class="help help-missing" title="Missing help: {escape(key)}">?</span>')

    title = escape(entry.get("title", ""))
    body = escape(entry.get("body", ""))
    example = escape(entry.get("example", ""))
    link = escape(entry.get("link", "")) if entry.get("link") else ""

    link_html = Markup("")
    if link:
        link_html = Markup(f'<a href="{link}" class="help-popover-link">Подробнее</a>')

    return Markup(
        "<details class=\"help-popover\">"
        "<summary class=\"help\" aria-label=\"help\">?</summary>"
        f"<div class=\"help-popover-card\"><strong>{title}</strong><p>{body}</p><p><em>{example}</em></p>{link_html}</div>"
        "</details>"
    )
