"""Tiny locale loader.

Every donor-facing string lives in ``app/locales/<lang>.yml`` and is fetched by dotted
key. No user-visible text is hardcoded in handlers, so adding Malayalam (PRD P1) is a
new file with the same keys plus a per-donor ``language`` column that already exists.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import settings

LOCALES_DIR = Path(__file__).parent / "locales"
FALLBACK = "en"


@lru_cache
def _catalogue(lang: str) -> dict[str, Any]:
    path = LOCALES_DIR / f"{lang}.yml"
    if not path.exists():
        path = LOCALES_DIR / f"{FALLBACK}.yml"
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _lookup(catalogue: dict[str, Any], key: str) -> Any:
    node: Any = catalogue
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def t(key: str, /, lang: str | None = None, **kwargs: Any) -> str:
    """Translate ``key``, interpolating ``kwargs``.

    Falls back to the default locale, then to the key itself, so a missing string is
    visible in testing rather than crashing a donor mid-flow.
    """
    lang = lang or settings.locale
    value = _lookup(_catalogue(lang), key)
    if value is None and lang != FALLBACK:
        value = _lookup(_catalogue(FALLBACK), key)
    if value is None:
        return key
    if isinstance(value, list):
        value = "\n".join(str(v) for v in value)
    text = str(value)
    return text.format(**kwargs) if kwargs else text


def tl(key: str, /, lang: str | None = None) -> list[str]:
    """Translate a key holding a list (district/city pickers)."""
    lang = lang or settings.locale
    value = _lookup(_catalogue(lang), key)
    if value is None and lang != FALLBACK:
        value = _lookup(_catalogue(FALLBACK), key)
    return list(value) if isinstance(value, list) else []
