from app.core.song_keys import ascii_latin, normalize_text, song_key


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
