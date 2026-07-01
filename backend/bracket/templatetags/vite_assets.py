import json
from functools import lru_cache
from pathlib import Path

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.safestring import mark_safe

register = template.Library()


def _manifest_candidates() -> list[Path]:
    candidates = [Path(settings.BASE_DIR) / "static" / "assets" / "manifest.json"]
    static_root = getattr(settings, "STATIC_ROOT", None)
    if static_root:
        candidates.append(Path(static_root) / "assets" / "manifest.json")
    return candidates


@lru_cache(maxsize=1)
def _load_manifest_cached() -> dict:
    for candidate in _manifest_candidates():
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError("Vite manifest was not found. Run `npm run build` in frontend first.")


def _load_manifest() -> dict:
    if settings.DEBUG:
        _load_manifest_cached.cache_clear()
    return _load_manifest_cached()


@register.simple_tag
def vite_entry(entry_name: str) -> str:
    manifest = _load_manifest()
    if entry_name not in manifest:
        raise KeyError(f"Vite entry '{entry_name}' is missing from manifest.json")

    entry = manifest[entry_name]
    tags: list[str] = []

    for css_file in entry.get("css", []):
        href = static(f"assets/{css_file}")
        tags.append(f'<link rel="stylesheet" href="{href}">')

    js_file = entry.get("file")
    if js_file:
        src = static(f"assets/{js_file}")
        tags.append(f'<script type="module" src="{src}"></script>')

    return mark_safe("\n".join(tags))
