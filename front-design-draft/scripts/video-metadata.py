"""Read selected public YouTube metadata without downloading video or audio."""
import json
import re
import sys
from urllib.request import Request, urlopen
sys.stdout.reconfigure(encoding='utf-8')
for video in sys.argv[1:]:
    html = urlopen(Request(f'https://www.youtube.com/watch?v={video}', headers={'User-Agent': 'Mozilla/5.0'}), timeout=25).read().decode()
    match = re.search(r'ytInitialPlayerResponse\s*=\s*(\{)', html)
    data = json.JSONDecoder().raw_decode(html[match.start(1):])[0]
    details = data.get('videoDetails', {})
    micro = data.get('microformat', {}).get('playerMicroformatRenderer', {})
    print(json.dumps({'id': video, 'title': details.get('title'), 'duration': details.get('lengthSeconds'), 'publish': micro.get('publishDate'), 'broadcast': micro.get('liveBroadcastDetails'), 'playability': data.get('playabilityStatus'), 'chapters': [line for line in details.get('shortDescription', '').splitlines() if re.search(r'\d+:\d{2}', line)]}, ensure_ascii=False))
