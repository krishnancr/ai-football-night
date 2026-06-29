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
}

# Reverse: any incoming alias -> FIFA canonical. Built from _SEARCH_NAME, plus
# aliases the schedule/media use that aren't a search-name flip (e.g. the
# English exonym "Ivory Coast" for the French official "Côte d'Ivoire").
_ALIAS_TO_CANONICAL = {v: k for k, v in _SEARCH_NAME.items()}
_ALIAS_TO_CANONICAL["Ivory Coast"] = "Côte d'Ivoire"

# Official FIFA three-letter trigrams, keyed by canonical name. The single source
# for per-match hashtags (#NEDJPN), where fans search the real code — a naive
# 3-char truncation (NET/JAP) is worse than useless. Covers the WC2026 field.
_FIFA_CODE = {
    "Argentina": "ARG", "Australia": "AUS", "Austria": "AUT", "Belgium": "BEL",
    "Bosnia and Herzegovina": "BIH", "Brazil": "BRA", "Cabo Verde": "CPV",
    "Cameroon": "CMR", "Canada": "CAN", "Chile": "CHI", "Colombia": "COL",
    "Costa Rica": "CRC", "Côte d'Ivoire": "CIV", "Croatia": "CRO",
    "Curaçao": "CUW", "Czechia": "CZE", "Denmark": "DEN", "Ecuador": "ECU",
    "Egypt": "EGY", "England": "ENG", "France": "FRA", "Germany": "GER",
    "Ghana": "GHA", "Haiti": "HAI", "Honduras": "HON", "Iran": "IRN",
    "Italy": "ITA", "Jamaica": "JAM", "Japan": "JPN", "Jordan": "JOR",
    "Korea Republic": "KOR", "Mexico": "MEX", "Morocco": "MAR",
    "Netherlands": "NED", "New Zealand": "NZL", "Nigeria": "NGA", "Norway": "NOR",
    "Panama": "PAN", "Paraguay": "PAR", "Peru": "PER", "Poland": "POL",
    "Portugal": "POR", "Qatar": "QAT", "Saudi Arabia": "KSA", "Scotland": "SCO",
    "Senegal": "SEN", "Serbia": "SRB", "South Africa": "RSA", "Spain": "ESP",
    "Sweden": "SWE", "Switzerland": "SUI", "Tunisia": "TUN", "Türkiye": "TUR",
    "Ukraine": "UKR", "United States": "USA", "Uruguay": "URU",
    "Uzbekistan": "UZB", "Wales": "WAL",
}


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


def fifa_code(name: str) -> str:
    """Official FIFA trigram for a team (e.g. 'NED'), via the canonical name.
    Falls back to the first three ASCII letters uppercased if unmapped."""
    canon = canonical(name)
    if canon in _FIFA_CODE:
        return _FIFA_CODE[canon]
    ascii_name = unicodedata.normalize("NFKD", canon).encode("ascii", "ignore").decode("ascii")
    return "".join(c for c in ascii_name if c.isalpha())[:3].upper()


def resolve(name: str) -> dict:
    c = canonical(name)
    return {"canonical": c, "search": search(c), "slug": slug(c)}


def candidate_slugs(name: str) -> list:
    """Every plausible on-disk slug for a team, to survive alias/exonym drift.

    A base file may have been generated with the canonical slug (e.g.
    'cote-divoire') OR an English exonym slug (e.g. 'ivory-coast'). Returns the
    canonical slug first, then the raw-name slug and any known-alias slugs that
    resolve to the same canonical, de-duplicated and order-preserving."""
    canon = canonical(name)
    cands = [slugify(canon), slugify(name)]
    # Any alias that maps to this canonical (e.g. 'Ivory Coast' -> Côte d'Ivoire).
    for alias, target in _ALIAS_TO_CANONICAL.items():
        if target == canon:
            cands.append(slugify(alias))
    seen, ordered = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def base_filename(home: str, away: str) -> str:
    """The on-disk base-context filename for a fixture (the '-vs-' convention)."""
    return f"wc_{slug(home)}-vs-{slug(away)}_base.json"
