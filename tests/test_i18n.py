import json
from pathlib import Path

import pytest

from backend.i18n import I18n, t


@pytest.fixture(autouse=True)
def reset_i18n():
    """Reset i18n state before each test."""
    I18n._strings = {}
    I18n._lang = "en"
    yield
    I18n._strings = {}
    I18n._lang = "en"


def test_load_english():
    config_dir = Path(__file__).parent.parent / "config"
    I18n.load("en", config_dir)
    assert I18n.lang() == "en"
    assert t("main.window_title") == "Football Annotation Tool"


def test_load_italian():
    config_dir = Path(__file__).parent.parent / "config"
    I18n.load("it", config_dir)
    assert I18n.lang() == "it"
    assert t("main.window_title") == "Strumento di Annotazione Calcio"


def test_load_german():
    config_dir = Path(__file__).parent.parent / "config"
    I18n.load("de", config_dir)
    assert I18n.lang() == "de"
    assert "Fußball" in t("main.window_title")


def test_load_portuguese():
    config_dir = Path(__file__).parent.parent / "config"
    I18n.load("pt", config_dir)
    assert I18n.lang() == "pt"
    assert "Futebol" in t("main.window_title")


def test_load_french():
    config_dir = Path(__file__).parent.parent / "config"
    I18n.load("fr", config_dir)
    assert I18n.lang() == "fr"
    assert "Football" in t("main.window_title")


def test_fallback_to_key():
    """Unknown keys return the key itself."""
    config_dir = Path(__file__).parent.parent / "config"
    I18n.load("en", config_dir)
    assert t("nonexistent.key") == "nonexistent.key"


def test_format_substitution():
    config_dir = Path(__file__).parent.parent / "config"
    I18n.load("en", config_dir)
    result = t("main.window_title_with_team",
               team_name="Test FC", folder_name="screenshots")
    assert "Test FC" in result
    assert "screenshots" in result


def test_fallback_to_english_for_unknown_lang():
    config_dir = Path(__file__).parent.parent / "config"
    I18n.load("xx", config_dir)  # unknown language
    assert t("main.window_title") == "Football Annotation Tool"


def test_all_languages_have_same_keys():
    """All language files must have the same set of keys."""
    i18n_dir = Path(__file__).parent.parent / "config" / "i18n"
    lang_files = sorted(i18n_dir.glob("*.json"))
    assert len(lang_files) >= 5, f"Expected at least 5 language files, got {len(lang_files)}"

    all_keys = {}
    for lang_file in lang_files:
        data = json.loads(lang_file.read_text(encoding="utf-8"))
        all_keys[lang_file.stem] = set(data.keys())

    en_keys = all_keys["en"]
    for lang, keys in all_keys.items():
        missing = en_keys - keys
        extra = keys - en_keys
        assert not missing, f"{lang}.json is missing keys: {missing}"
        assert not extra, f"{lang}.json has extra keys: {extra}"
