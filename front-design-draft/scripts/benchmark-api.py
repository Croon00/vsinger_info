"""Read-only HTTP measurements. Never calls legacy live detail (which writes)."""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.core.config import settings
import httpx

mode = sys.argv[1] if len(sys.argv) > 1 else 'before'
prefix = '/api/v2' if mode == 'after' else '/api'
results = []
with httpx.Client(base_url=os.environ.get('BENCHMARK_API_URL','http://127.0.0.1:8000'), timeout=120,
                  headers={'X-API-Key': settings.api_key} if settings.api_key else {}) as client:
    def measure(label, path):
        start = time.perf_counter()
        r = client.get(path)
        entry = {'label': label, 'ms': round((time.perf_counter()-start)*1000),
                 'status': r.status_code, 'bytes': len(r.content), 'timing': r.headers.get('server-timing')}
        results.append(entry)
        print(json.dumps(entry), flush=True)
        r.raise_for_status()
        return r.json()
    artists_path = prefix + '/artists' + ('?grouped=true' if mode == 'before' else '')
    catalog = measure('artists cold', artists_path)
    measure('artists repeat', artists_path)
    items = catalog if isinstance(catalog, list) else catalog['items']
    target = next((a for a in items if a['name'].upper() == 'HACHI'), items[0])
    aid = target['id']
    if mode == 'before':
        from urllib.parse import urlencode
        measure('artist archives all', '/api/youtube-lives?' + urlencode({'artist_name':target['name'],'all_records':'true'}))
        measure('search title', '/api/youtube-performances?song_title=Song&limit=500')
        measure('search original', '/api/youtube-performances?original_artist=Song&limit=500')
        measure('concerts ready', '/api/event-candidates?event_type=live_event&status_filter=ready')
    else:
        measure('artist archives first page', f'{prefix}/artists/{aid}/lives?limit=6')
        measure('artist statistics', f'{prefix}/artists/{aid}/statistics')
        measure('search OR', prefix+'/search?q=Song&limit=50')
        measure('concerts', prefix+'/concerts')
    (Path(__file__).resolve().parents[1]/'docs'/f'performance-{mode}.json').write_text(json.dumps(results, indent=2), encoding='utf8')
