from app.integrations.youtube_live_archive import _timestamp_to_seconds, clean_setlist_title, parse_setlist_comment
from app.integrations.karaoke_lookup import split_song_credit


def test_parse_setlist_comment_extracts_timestamped_songs() -> None:
    comment = """
    セットリスト
    0:42 - First Song
    12:03　Second Song
    1:04:59 | Third Song
    ご視聴ありがとうございました
    """

    assert parse_setlist_comment(comment) == [
        {"timestamp": "0:42", "title": "First Song"},
        {"timestamp": "12:03", "title": "Second Song"},
        {"timestamp": "1:04:59", "title": "Third Song"},
    ]


def test_parse_setlist_comment_ignores_comment_without_timestamps() -> None:
    assert parse_setlist_comment("楽しい配信でした！") == []


def test_parse_setlist_comment_accepts_numbered_rows() -> None:
    assert parse_setlist_comment("4  . 07:36 アポリア/ヨルシカ") == [
        {"timestamp": "07:36", "title": "アポリア/ヨルシカ"}
    ]


def test_parse_setlist_comment_accepts_arbitrary_prefixes() -> None:
    comment = """
    🎵 M4 [추천] 07:36 アポリア/ヨルシカ
    ▶ 네 번째 곡은 12:57 若者のすべて/フジファブリック
    """
    assert parse_setlist_comment(comment) == [
        {"timestamp": "07:36", "title": "アポリア/ヨルシカ"},
        {"timestamp": "12:57", "title": "若者のすべて/フジファブリック"},
    ]


def test_clean_setlist_title_removes_accidentally_captured_timestamp() -> None:
    assert clean_setlist_title("02:11:35 僕が死のうと思ったのは") == "僕が死のうと思ったのは"
    assert clean_setlist_title("00:02 00:12 #17 新世界") == "#17 新世界"
    assert clean_setlist_title("00:10:52 00:16:24 00:23:43") == ""


def test_clean_setlist_title_removes_setlist_noise() -> None:
    assert clean_setlist_title("#01 天体観測") == "天体観測"
    assert clean_setlist_title("04 #10 カルマ") == "カルマ"
    assert clean_setlist_title("26 #3 又三郎") == "又三郎"
    assert clean_setlist_title("- 02:24:52 境界線") == "境界線"
    assert clean_setlist_title("~ 00:48:20 ワンルーム叙事詩") == "ワンルーム叙事詩"
    assert clean_setlist_title("、BUMPツアーチケットもっと当てたい 01:27:4") == "BUMPツアーチケットもっと当てたい"
    assert clean_setlist_title("@25人") == ""
    assert clean_setlist_title("(please) forgive") == "(please) forgive"
    assert clean_setlist_title(", 0:15:04 , 0:15:43 ,") == ""
    assert clean_setlist_title("00 0:00") == ""
def test_parse_setlist_comment_keeps_only_song_and_artist_from_timestamp_ranges() -> None:
    comment = """
    1曲目 08:36~13:14「変わらないもの／奥華子」 95.192点
    2曲目 15:57〜20:39『茜色の約束 / いきものがかり』 96.446点
    """

    assert parse_setlist_comment(comment) == [
        {"timestamp": "08:36", "title": "変わらないもの/奥華子"},
        {"timestamp": "15:57", "title": "茜色の約束 / いきものがかり"},
    ]


def test_timestamp_to_seconds_supports_hour_timestamp() -> None:
    assert _timestamp_to_seconds("1:04:59") == 3899
    assert _timestamp_to_seconds("12:03") == 723


def test_split_song_credit_allows_missing_artist() -> None:
    assert split_song_credit("アイドル / YOASOBI") == ("アイドル", "YOASOBI")
    assert split_song_credit("名前のない歌") == ("名前のない歌", None)
    assert split_song_credit("アポリア/ヨルシカ") == ("アポリア", "ヨルシカ")
    assert split_song_credit("雨うつつ/") == ("雨うつつ", None)
