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
