"""Refresh the selected public media metadata; never contacts the project backend."""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote
sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parent.parent
def fetch(url):
    return urlopen(Request(quote(url, safe=':/?=&%'), headers={'User-Agent': 'Mozilla/5.0'}), timeout=30).read()
class Images(HTMLParser):
    def __init__(self):
        super().__init__(); self.images = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'img': self.images.append(a)
if __name__ == '__main__':
    page = Images(); page.feed(fetch('https://linkco.re/t3pG1pgu?lang=en').decode())
    cover = next(i['src'] for i in page.images if 'Front Cover' in i.get('alt', ''))
    targets = {
        'midnight-blue.jpg': cover,
        'kaf-butte.png': 'https://kamitsubaki.jp/wp-content/uploads/2025/06/butte_JKT-1400x1400.png',
        'kaf-eat.jpg': 'https://kamitsubaki.jp/wp-content/uploads/2025/06/EATTHEPAST_Thumbnail-1400x1400.jpg',
        'kaf-my-life.jpg': 'https://kamitsubaki.jp/wp-content/uploads/2025/01/KAFxMoeShop_MYLIFE_JKT-1400x1400.jpg',
    }
    dest = ROOT / 'public/images/albums'; dest.mkdir(exist_ok=True)
    for filename, url in targets.items():
        (dest / filename).write_bytes(fetch(url))
    (ROOT / 'docs/album-sources.json').write_text(json.dumps(targets, ensure_ascii=False, indent=2), encoding='utf-8')
    for video in ['s6BZdVRPH_o', 'Ycu3iehv_ow']:
        html = fetch(f'https://www.youtube.com/watch?v={video}').decode()
        match = re.search(r'ytInitialPlayerResponse\s*=\s*(\{)', html)
        payload = json.JSONDecoder().raw_decode(html[match.start(1):])[0]
        details = payload['videoDetails']
        micro = payload.get('microformat', {}).get('playerMicroformatRenderer', {})
        print(json.dumps({'id': video, 'title': details['title'], 'duration': details['lengthSeconds'], 'publish': micro.get('publishDate'), 'broadcast': micro.get('liveBroadcastDetails'), 'chapters': [line for line in details.get('shortDescription', '').splitlines() if re.search(r'\d+:\d{2}', line)]}, ensure_ascii=False))
