import json
from pathlib import Path
from typing import Optional


class I18n:
    """Simple JSON-based internationalization."""

    _strings: dict[str, str] = {}
    _lang: str = "en"

    @classmethod
    def load(cls, lang: str = "en", config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "config"
        lang_file = config_dir / "i18n" / f"{lang}.json"
        if not lang_file.exists():
            lang_file = config_dir / "i18n" / "en.json"
        if lang_file.exists():
            cls._strings = json.loads(lang_file.read_text(encoding="utf-8"))
        cls._lang = lang

    @classmethod
    def t(cls, key: str, **kwargs) -> str:
        text = cls._strings.get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text
        return text

    @classmethod
    def lang(cls) -> str:
        return cls._lang


def t(key: str, **kwargs) -> str:
    return I18n.t(key, **kwargs)
