"""Fetch public artist profile assets from the two official label sites.
No credentials, backend, or existing frontend assets are used.
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8')

def fetch(url):
    url = quote(url, safe=':/?=&%')
    return urlopen(Request(url, headers={'User-Agent': 'schedule-music-design-preview/0.1'}), timeout=30).read()

class Page(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.images = []
        self.links = []
        self.feed(content)
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'img' and attrs.get('src'):
            self.images.append(attrs)
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])

rk = Page(fetch('https://rkmusic.jp/artist/').decode())
kam = Page(fetch('https://kamitsubaki.jp/artist/').decode())
entries = [
    (1, 'HACHI', '하치', 'HACHI', 'RK Music', 'https://rkmusic.jp/artist/227/', '01-16'),
    (2, '花譜', '카후', 'KAF', 'KAMITSUBAKI STUDIO', 'https://kamitsubaki.jp/artist/kaf/', None),
    (3, '瀬戸乃 とと', '세토노 토토', 'SETONO TOTO', 'RK Music', 'https://rkmusic.jp/artist/219/', '10-10'),
    (4, '理芽', '리메', 'RIM', 'KAMITSUBAKI STUDIO', 'https://kamitsubaki.jp/artist/rim/', None),
    (5, 'VESPERBELL', '베스퍼벨', 'VESPERBELL', 'RK Music', 'https://rkmusic.jp/artist/286/', None),
    (6, 'ヰ世界情緒', '이세계정서', 'ISEKAIJOUCHO', 'KAMITSUBAKI STUDIO', 'https://kamitsubaki.jp/artist/isekaijoucho/', None),
    (7, '焔魔 るり', '엔마 루리', 'ENMA RURI', 'RK Music', None, None),
    (8, '春猿火', '하루사루히', 'HARUSARUHI', 'KAMITSUBAKI STUDIO', 'https://kamitsubaki.jp/artist/harusaruhi/', None),
    (9, '水瀬 凪', '미나세 나기', 'MINASE NAGI', 'RK Music', None, None),
    (10, '幸祜', '코코', 'KOKO', 'KAMITSUBAKI STUDIO', 'https://kamitsubaki.jp/artist/koko/', None),
    (11, 'KMNZ', '케모노즈', 'KMNZ', 'RK Music', None, None),
    (12, '明透', '아스', 'ASU', 'KAMITSUBAKI STUDIO', 'https://kamitsubaki.jp/artist/asu/', None),
]
rk_html = fetch('https://rkmusic.jp/artist/').decode()
assets = ROOT / 'public' / 'images' / 'artists'
assets.mkdir(parents=True, exist_ok=True)
result = []
for id, name, ko, roman, agency, official, birthday in entries:
    if not official:
        # Each profile card links directly to a numeric artist page.
        match = re.search(r'<a[^>]+href="(https://rkmusic.jp/artist/\d+/)"[^>]*>(?:(?!</a>).)*alt="'+re.escape(name)+r'"', rk_html, re.S)
        official = match.group(1) if match else 'https://rkmusic.jp/artist/'
    try:
        content = fetch(official).decode()
        page = Page(content)
        image = next((i['src'] for i in (rk.images if agency == 'RK Music' else page.images) if i.get('alt') == name), None)
        if not image:
            image = next(i['src'] for i in page.images if 'uploads/' in i['src'])
        image = urljoin(official, image)
        ext = Path(urlsplit(image).path).suffix
        filename = f'{id}{ext}'
        (assets / filename).write_bytes(fetch(image))
        links = [{'label': '공식 사이트', 'url': official}]
        for label, domain in [('YouTube', 'youtube.com/'), ('X', 'twitter.com/')]:
            link = next((u for u in page.links if domain in u), None)
            if link:
                links.append({'label': label, 'url': link})
        if not birthday:
            b = re.search(r'誕生日[：:]\s*(\d+)月(\d+)日', content)
            if b and name != 'VESPERBELL':
                birthday = f'{int(b[1]):02d}-{int(b[2]):02d}'
        result.append(dict(id=id, name=name, display_name=ko, roman=roman, agency=agency,
            image=f'/images/artists/{filename}', image_source=image, official_url=official,
            links=links, birthday=birthday))
        print(f'{id}: {name} — saved', flush=True)
    except Exception as e:
        print(f'{id}: {name} ERROR {e}', flush=True)
(ROOT / 'src' / 'mocks').mkdir(parents=True, exist_ok=True)
(ROOT / 'src' / 'mocks' / 'artists.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
