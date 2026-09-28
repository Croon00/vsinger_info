from datetime import date, datetime, timedelta, timezone

from app.integrations.live_site_pages import event_links, parse_live_detail
from app.repositories.public_lives import artist_ids_for_event


def test_channel_links_ignore_global_recommendations_and_duplicates():
    html = """
    <a href="/ko/live/detail/1">site recommendation</a>
    <h2>최신 이벤트</h2>
    <a href="/ko/live/detail/10960">VIIIHIVE</a>
    <h2>기타 이벤트</h2>
    <a href="/ja/live/detail/10960?ref=channel">VIIIHIVE again</a>
    <a href="https://other.example/ko/live/detail/2">outside host</a>
    """
    assert event_links("https://www.zan-live.com/ko/channel/rkmusic", html) == [
        "https://www.zan-live.com/ko/live/detail/10960"
    ]


def test_zan_detail_preserves_midnight_jst_date_and_source_url():
    url = "https://www.zan-live.com/ko/live/detail/10960"
    html = """
    <meta property="og:title" content="VIIIHIVE Showcase - Z-aN">
    <h1>VIIIHIVE Showcase</h1>
    <p>개최일： 2026년 10월 11일(일) 공연 시작 시간(00:30)개장 00:00(JST)</p>
    <section>出演者 HACHI / 水槽</section><section>会場 代官山UNIT</section>
    """
    event = parse_live_detail(url, html)
    assert event is not None
    assert event.source_url == url
    assert event.title == "VIIIHIVE Showcase"
    assert event.event_date == date(2026, 10, 11)
    assert event.starts_at == datetime(2026, 10, 11, 0, 30, tzinfo=timezone(timedelta(hours=9)))


def test_structured_online_event_is_calendar_ready():
    html = """
    <script type="application/ld+json">{"@type":"Event","name":"RIM LIVE",
      "startDate":"2026-11-02T19:00:00+09:00"}</script>
    <p>Streaming online</p>
    """
    event = parse_live_detail("https://riotmusic-live.zaiko.io/e/rim-live", html)
    assert event is not None
    assert event.event_date == date(2026, 11, 2)
    assert event.event_format == "online"


def test_riot_official_article_falls_back_when_zaiko_listing_is_blocked():
    index = '<a href="/mugensho-record/info/223/">festival</a>'
    assert event_links("https://riot-music.com/mugensho-record/info/", index) == [
        "https://riot-music.com/mugensho-record/info/223/"
    ]
    article = """
    <meta property="og:title" content="無原唱レコードフェス2026 RE;GAIN">
    <h1>無原唱レコードフェス2026 RE;GAIN</h1>
    <p>公演日時：2026.11.26(木) 開場 17:00 / 開演 18:00</p>
    <p>出演者 松永依織 朝倉杏子</p>
    <a href="https://riotmusic-live.zaiko.io/e/regain">チケット</a>
    """
    event = parse_live_detail("https://riot-music.com/mugensho-record/info/223/", article)
    assert event is not None
    assert event.event_date == date(2026, 11, 26)
    assert event.ticket_url == "https://riotmusic-live.zaiko.io/e/regain"


def test_channel_owner_and_explicit_guest_match_without_unrelated_artist():
    rows = [
        {"id": 1, "name_native": "花譜", "name_ko": None, "name_latin": "KAF", "aliases": []},
        {"id": 2, "name_native": "理芽", "name_ko": None, "name_latin": "RIM", "aliases": []},
        {"id": 3, "name_native": "HACHI", "name_ko": None, "name_latin": None, "aliases": []},
    ]
    event = parse_live_detail("https://www.zan-live.com/ko/live/detail/1", """
      <meta property="og:title" content="KAF and RIM LIVE - Z-aN">
      <p>개최일 2026년 11월 2일(월) 공연 시작 시간(19:00)</p>
    """)
    assert event is not None
    assert artist_ids_for_event(rows, "virtual_kaf", event) == [1, 2]
