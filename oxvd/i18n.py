"""Tiny JSON-based translation layer. Keys are English UI strings.
Each language lives in its own file: local/<code>.json ."""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_DIR = os.path.join(ROOT, "local")

# (code, native name) — native names are never translated
LANGS = [
    ("ru", "Русский"),
    ("en", "English"),
    ("es", "Español"),
    ("fr", "Français"),
    ("de", "Deutsch"),
]

_TR = {}
_PL = {}
LANG = "en"


def set_lang(code):
    global _TR, _PL, LANG
    LANG = code
    path = os.path.join(LOCAL_DIR, code + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    _PL = data.pop("__plurals__", {})
    _TR = data


def T(s):
    """Translate a string; falls back to the English key."""
    return _TR.get(s, s)


def plural(key, n, fallback=("task", "tasks")):
    """Pick the right noun form for a count. JSON lists 2 (en/es/fr/de-like)
    or 3 (Slavic) forms: [one, few, many]."""
    forms = _PL.get(key) or list(fallback)
    if len(forms) == 2:
        return forms[0] if n == 1 else forms[1]
    m10, m100 = n % 10, n % 100
    if m10 == 1 and m100 != 11:
        return forms[0]
    if 2 <= m10 <= 4 and not 12 <= m100 <= 14:
        return forms[1]
    return forms[2]
