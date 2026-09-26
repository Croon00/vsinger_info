from app.core.song_keys import normalize_text, song_key


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
