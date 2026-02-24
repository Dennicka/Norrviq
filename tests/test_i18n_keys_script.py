import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("check_i18n_keys", Path("scripts/check_i18n_keys.py"))
check_i18n_keys = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(check_i18n_keys)


def test_translation_key_coverage_passes_for_current_dictionaries():
    assert check_i18n_keys.check_key_coverage() == []


def test_translation_key_coverage_fails_when_key_missing(monkeypatch):
    fake_langs = {
        "ru": {"x": "1"},
        "sv": {},
        "en": {"x": "1"},
    }
    monkeypatch.setattr(check_i18n_keys, "LANGS", fake_langs)
    errors = check_i18n_keys.check_key_coverage()
    assert errors
    assert "[sv] missing keys: x" in errors[0]
