from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.i18n import TRANSLATIONS_EN, TRANSLATIONS_RU, TRANSLATIONS_SV  # noqa: E402

LANGS = {"ru": TRANSLATIONS_RU, "sv": TRANSLATIONS_SV, "en": TRANSLATIONS_EN}


def check_key_coverage() -> list[str]:
    errors: list[str] = []
    all_keys = set().union(*(d.keys() for d in LANGS.values()))
    for lang, data in LANGS.items():
        missing = sorted(all_keys - set(data.keys()))
        if missing:
            errors.append(f"[{lang}] missing keys: {', '.join(missing)}")
    return errors


def scan_template_keys() -> list[str]:
    missing: list[str] = []
    pattern = re.compile(r"t\(\s*['\"]([^'\"]+)['\"]\s*\)")
    all_keys = set().union(*(d.keys() for d in LANGS.values()))
    for path in Path("app/templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for key in pattern.findall(text):
            if "~" in key or "{" in key:
                continue
            if key not in all_keys:
                missing.append(f"{path}: missing key '{key}'")
    return missing


def main() -> int:
    coverage_errors = check_key_coverage()
    template_warnings = scan_template_keys()

    if coverage_errors:
        print("Translation key mismatch:")
        for err in coverage_errors:
            print(f" - {err}")
    if template_warnings:
        print("Template key warnings:")
        for warning in template_warnings:
            print(f" - {warning}")

    return 1 if coverage_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
