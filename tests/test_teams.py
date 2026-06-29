def test_canonical_passthrough_for_unknown():
    import teams
    assert teams.canonical("Brazil") == "Brazil"

def test_search_name_override():
    import teams
    assert teams.search("Korea Republic") == "South Korea"
    assert teams.search("Czechia") == "Czech Republic"
    assert teams.search("Türkiye") == "Turkey"
    assert teams.search("Cabo Verde") == "Cape Verde"

def test_search_passthrough_when_no_override():
    import teams
    assert teams.search("Brazil") == "Brazil"

def test_slug_is_canonical_lowercased_hyphenated():
    import teams
    assert teams.slug("Korea Republic") == "korea-republic"
    assert teams.slug("Bosnia and Herzegovina") == "bosnia-and-herzegovina"
    assert teams.slug("Côte d'Ivoire") == "cote-divoire"

def test_resolve_alias_back_to_canonical():
    import teams
    assert teams.resolve("Czech Republic")["canonical"] == "Czechia"
    assert teams.resolve("South Korea")["canonical"] == "Korea Republic"

def test_base_filename_helper():
    import teams
    assert teams.base_filename("Korea Republic", "Czechia") == "wc_korea-republic-vs-czechia_base.json"

def test_candidate_slugs_includes_canonical_and_exonym():
    import teams
    # 'Ivory Coast' base files on disk use the English exonym slug, but slug()
    # returns the canonical 'cote-divoire'. candidate_slugs must offer both.
    cands = teams.candidate_slugs("Ivory Coast")
    assert "cote-divoire" in cands
    assert "ivory-coast" in cands
    # Passing the canonical name must surface the exonym slug too.
    assert "ivory-coast" in teams.candidate_slugs("Côte d'Ivoire")

def test_candidate_slugs_dedupes_simple_name():
    import teams
    assert teams.candidate_slugs("Brazil") == ["brazil"]
