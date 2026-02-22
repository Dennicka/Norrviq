from pathlib import Path
import re

from app.help.registry import HELP_TEXT


def test_help_registry_has_ru_for_all_keys():
    assert HELP_TEXT
    for key, translations in HELP_TEXT.items():
        assert "ru" in translations, f"{key} must include ru"
        ru = translations["ru"]
        for field in ("title", "body", "example"):
            assert ru.get(field), f"{key}.ru.{field} is required"


def test_help_keys_used_in_templates_exist_in_registry():
    root = Path("app/templates")
    pattern = re.compile(r"help_icon\(\s*['\"]([^'\"]+)['\"]\s*\)")
    used_keys: set[str] = set()

    for template in root.rglob("*.html"):
        text = template.read_text(encoding="utf-8")
        used_keys.update(pattern.findall(text))

    missing = sorted(key for key in used_keys if key not in HELP_TEXT)
    assert not missing, f"Missing help registry keys: {missing}"
