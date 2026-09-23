"""Explicit read-only transaction; report aggregate timings, never SQL/records."""
import json
import sys
from collections import defaultdict
from pathlib import Path
from time import perf_counter
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from sqlalchemy import event
from sqlalchemy.orm import Session
from app.db.session import get_engine
from app.services.artist_service import ArtistService
from app.services.read_catalog import ReadCatalog

engine=get_engine()
results={}
for name,loader in [('legacy',lambda s:ArtistService(s).list_artists(grouped=True)),('v2',lambda s:ReadCatalog(s).artists())]:
    counts=defaultdict(lambda:{'queries':0,'ms':0})
    def before(conn,cursor,statement,parameters,context,executemany):
        context.benchmark_start=perf_counter()
    def after(conn,cursor,statement,parameters,context,executemany):
        group='representative_video' if 'SELECT y.youtube_url' in statement else 'sources' if 'artist_sources' in statement else 'artists'
        counts[group]['queries']+=1
        counts[group]['ms']+=(perf_counter()-context.benchmark_start)*1000
    with Session(engine) as session:
        session.connection().exec_driver_sql('SET TRANSACTION READ ONLY')
        event.listen(engine,'before_cursor_execute',before)
        event.listen(engine,'after_cursor_execute',after)
        try:
            start=perf_counter()
            data=loader(session)
            results[name]={'total_ms':round((perf_counter()-start)*1000),'artists':len(data),'groups':dict(counts)}
        finally:
            event.remove(engine,'before_cursor_execute',before)
            event.remove(engine,'after_cursor_execute',after)
            session.rollback()
print(json.dumps(results,indent=2))
(Path(__file__).resolve().parents[1]/'docs/performance-queries.json').write_text(json.dumps(results,indent=2),encoding='utf8')
