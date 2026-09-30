from app.core.song_keys import ascii_latin, lookup_keys, normalize_text, resolve_key, song_key


def test_width_case_space_and_wrapping_quotes_are_normalized():
    assert normalize_text("  ＬＥＭＯＮ  ") == "lemon"
    assert normalize_text("「夜に駆ける」") == "夜に駆ける"
    assert normalize_text("『 シャル  ル 』") == "シャル ル"
    assert normalize_text('"「Lemon」"') == "lemon"


def test_different_spellings_stay_different():
    assert normalize_text("夜に駆ける") != normalize_text("よるにかける")
    assert normalize_text("Lemon (cover)") == "lemon (cover)"
    assert normalize_text("「A」と「B」") == "「a」と「b」"


def test_missing_values_and_key_shape():
    assert normalize_text(None) == "" and normalize_text("   ") == ""
    assert song_key("Lemon", None) == ("lemon", "")
    assert song_key("Lemon", " 米津玄師 ") == ("lemon", "米津玄師")


def test_ascii_latin_strips_marks_and_rejects_non_latin():
    assert ascii_latin("Tōkyō  Flash") == "Tokyo Flash"
    assert ascii_latin("Beyoncé") == "Beyonce"
    assert ascii_latin("ＤＥＣＯ＊２７") == "DECO*27"
    assert ascii_latin("Lost One no Goukoku") == "Lost One no Goukoku"
    assert ascii_latin("夜に駆ける") is None
    assert ascii_latin("Heart ♡") is None
    assert ascii_latin("") is None and ascii_latin(None) is None



def test_lookup_keys_offer_splits_only_without_artist():
    assert lookup_keys("Lemon", "米津玄師") == [("lemon", "米津玄師")]
    assert lookup_keys("怪獣  /  サカナクション", None) == [("怪獣 / サカナクション", ""), ("怪獣", "サカナクション")]
    assert lookup_keys("からくりピエロ/40mP", None)[1] == ("からくりピエロ", "40mp")
    assert lookup_keys("Flavor Of Life - 宇多田ヒカル", None)[1] == ("flavor of life", "宇多田ヒカル")
    assert lookup_keys("W/X/Y", None) == [("w/x/y", ""), ("w", "x/y"), ("w/x", "y")]
    assert lookup_keys("ロキ-みきとP", None) == [("ロキ-みきとp", "")]   # unspaced hyphen is part of titles
    assert lookup_keys("/ Artist", None) == [("/ artist", "")]


def test_lookup_keys_drop_setlist_numbering():
    assert lookup_keys("＃10 二息歩行 / DECO*27", None) == [
        ("#10 二息歩行 / deco*27", ""), ("二息歩行 / deco*27", ""), ("#10 二息歩行", "deco*27"), ("二息歩行", "deco*27")]
    assert lookup_keys("#3 夜明けと蛍", "n-buna") == [("#3 夜明けと蛍", "n-buna"), ("夜明けと蛍", "n-buna")]
    assert lookup_keys("55", "Official髭男dism") == [("55", "official髭男dism")]      # a number title stays
    assert lookup_keys("20 fragments", None) == [("20 fragments", "")]              # no hash: part of the title
    assert lookup_keys("#KMNZ", None) == [("#kmnz", "")]


def test_resolve_key_prefers_exact_and_refuses_ambiguous_splits():
    exact, split = ("w/x/y", ""), ("w/x", "y")
    assert resolve_key([exact, split], {exact: 1, split: 2}) == exact
    assert resolve_key([exact, split], {split: 2}) == split
    other = ("w", "x/y")
    assert resolve_key([exact, other, split], {other: 3, split: 3}) == other   # both name one song
    assert resolve_key([exact, other, split], {other: 3, split: 2}) is None    # different songs
    assert resolve_key([exact], {}) is None and resolve_key([], {}) is None