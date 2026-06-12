"""Single source of truth for team-name identity.

FIFA writes official names (schedule.json) that sports media — and Tavily —
spell differently, and base-context files key off a canonical slug. Every
name-sensitive subsystem (research queries, base join, result fetch, display)
routes through this module so a 'Czechia' vs 'Czech Republic' mismatch can
never again silently break the data join.
"""
import unicodedata

# FIFA official name -> the name media / Tavily use.
_SEARCH_NAME = {
    "Korea Republic": "South Korea",
    "Türkiye": "Turkey",
    "Cabo Verde": "Cape Verde",
    "Czechia": "Czech Republic",
    "IR Iran": "Iran",
    "China PR": "China",
}

# Reverse: any incoming alias -> FIFA canonical. Built from _SEARCH_NAME.
_ALIAS_TO_CANONICAL = {v: k for k, v in _SEARCH_NAME.items()}


def slugify(text: str) -> str:
    """ASCII, lowercase, hyphenated, apostrophes/accents stripped."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower().replace(" ", "-").replace("'", "").replace(".", "")


def canonical(name: str) -> str:
    """Normalize any alias to the FIFA official name; passthrough if unknown."""
    return _ALIAS_TO_CANONICAL.get(name, name)


def search(name: str) -> str:
    """The name to use in Tavily/web queries."""
    return _SEARCH_NAME.get(canonical(name), canonical(name))


def slug(name: str) -> str:
    """Stable slug for base-file joins, keyed off the canonical name."""
    return slugify(canonical(name))


def resolve(name: str) -> dict:
    c = canonical(name)
    return {"canonical": c, "search": search(c), "slug": slug(c)}


def base_filename(home: str, away: str) -> str:
    """The on-disk base-context filename for a fixture (the '-vs-' convention)."""
    return f"wc_{slug(home)}-vs-{slug(away)}_base.json"
