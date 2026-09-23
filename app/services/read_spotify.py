"""Bounded, successful-result-only cache for external catalogue reads."""
import asyncio
from collections import OrderedDict
from time import monotonic
from app.integrations.spotify import get_artist_discography, get_album_detail

class ReadCache:
    def __init__(self, ttl=300, capacity=128):
        self.ttl, self.capacity = ttl, capacity
        self.values = OrderedDict()
        self.pending = {}

    async def get(self, key, loader):
        now = monotonic()
        item = self.values.get(key)
        if item and item[0] > now:
            self.values.move_to_end(key)
            return item[1]
        self.values.pop(key, None)
        if key not in self.pending:
            async def fill():
                try:
                    value = await loader()
                    self.values[key] = (monotonic()+self.ttl, value)
                    while len(self.values)>self.capacity:
                        self.values.popitem(last=False)
                    return value
                finally:
                    self.pending.pop(key,None)
            self.pending[key] = asyncio.create_task(fill())
        return await asyncio.shield(self.pending[key])

cache = ReadCache()

async def discography(spotify_id):
    return await cache.get(('artist',spotify_id), lambda:get_artist_discography(spotify_id))

async def album(album_id):
    # Legacy album lookup can translate/write. v2 explicitly disables enrichment.
    return await cache.get(('album',album_id), lambda:get_album_detail(album_id, enrich_titles=False))
