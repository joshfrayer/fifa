import json
import logging
from functools import lru_cache
from pathlib import Path

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.safestring import mark_safe

register = template.Library()
logger = logging.getLogger(__name__)


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


def _collect_css_files(manifest: dict, entry_key: str, seen: set[str] | None = None) -> list[str]:
    seen = seen or set()
    if entry_key in seen:
        return []
    seen.add(entry_key)

    entry = manifest.get(entry_key) or {}
    css_files: list[str] = list(entry.get("css", []))

    for import_key in entry.get("imports", []):
        css_files.extend(_collect_css_files(manifest, import_key, seen))

    return css_files


def _asset_href(relative_path: str) -> str:
    try:
        return static(relative_path)
    except Exception:
        if settings.DEBUG:
            raise
        static_url = settings.STATIC_URL if settings.STATIC_URL.endswith("/") else f"{settings.STATIC_URL}/"
        return f"{static_url}{relative_path}"


@register.simple_tag
def vite_entry(entry_name: str) -> str:
    try:
        manifest = _load_manifest()
    except Exception as exc:
        if settings.DEBUG:
            raise
        logger.exception("Unable to load Vite manifest; rendering without bundled assets: %s", exc)
        return ""

    if entry_name not in manifest:
        if settings.DEBUG:
            raise KeyError(f"Vite entry '{entry_name}' is missing from manifest.json")
        logger.error("Vite entry '%s' missing from manifest.json; rendering without bundled assets", entry_name)
        return ""

    entry = manifest[entry_name]
    tags: list[str] = []
    emitted_css: set[str] = set()

    for css_file in _collect_css_files(manifest, entry_name):
        if css_file in emitted_css:
            continue
        emitted_css.add(css_file)
        href = _asset_href(f"assets/{css_file}")
        tags.append(f'<link rel="stylesheet" href="{href}">')

    js_file = entry.get("file")
    if js_file:
        src = _asset_href(f"assets/{js_file}")
        tags.append(f'<script type="module" src="{src}"></script>')

    return mark_safe("\n".join(tags))
