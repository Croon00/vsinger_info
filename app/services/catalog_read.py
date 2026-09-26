"""Map the normalized catalog to frontend read contracts."""
from app.repositories.catalog_read import CatalogReadRepository
from app.services.avatar_assets import avatar_variants, public_base

class CatalogRead:
    def __init__(self, session):
        self.repository = CatalogReadRepository(session)
        self._artists = None
    @property
    def query_ms(self): return self.repository.query_ms
    @property
    def query_count(self): return self.repository.query_count

    def artists(self):
        if self._artists is None:
            self._artists = self.repository.artists()
            image_base = public_base()
            for artist in self._artists:
                artist["avatar_variants"] = avatar_variants(artist.get("spotify_image_url"), image_base)
        return self._artists
    def artist(self, artist_id):
        return next((a for a in self.artists() if a["id"]==artist_id), None)
    def lives(self, artist_id, offset, limit):
        result = self.repository.lives(artist_id,offset,limit)
        for row in result["items"]:
            row["artist_id"] = artist_id
        return result
    def live(self, key): return self.repository.live(key)
    def search(self, q, offset, limit): return self.repository.search(q,offset,limit)
    def concerts(self, offset, limit, artist_id=None, start=None, end=None):
        return self._concert_dates(self.repository.concerts(offset,limit,artist_id,start,end))
    def concert(self, key):
        rows = self._concert_dates(self.repository.concerts(0,1,key=key))["items"]
        return rows[0] if rows else None
    @staticmethod
    def _concert_dates(page):
        for row in page["items"]:
            value = row["starts_at"] or row.pop("event_date", None)
            row["starts_at"] = value.isoformat() if value else ""
        return page
    def albums(self, artist_id): return self.repository.albums(artist_id=artist_id)
    def album(self, key):
        rows = self.repository.albums(key=key)
        if not rows: return None
        rows[0]["tracks"] = self.repository.tracks(key)
        return rows[0]
    def lyrics(self, key): return self.repository.lyrics(key)

    def statistics(self, artist_id):
        rows, months = self.repository.statistic_rows(artist_id)
        songs, originals = [], {}
        rank, previous = 0, None
        for index,row in enumerate(rows):
            if previous != row["count"]: rank = index+1
            previous = row["count"]
            songs.append({"key":row["song_key"],"title":row["title"],"titleKo":row["title_ko"],
                          "artist":row["artist"],"artistKo":row["artist_ko"],
                          "searchText":row["search"],"count":row["count"],"rank":rank,"lastPerformedAt":row["last_date"]})
            for artist in row["originals"]:
                entry = originals.setdefault(artist["key"],{**artist,"count":0})
                entry["nameKo"] = entry.get("nameKo") or artist.get("nameKo")
                entry["count"] += row["count"]
        total = sum(s["count"] for s in songs)
        ranked = sorted(originals.values(),key=lambda a:(-a["count"],a["key"]))
        for artist in ranked: artist["percentage"] = artist["count"]/total*100 if total else 0
        return {"archives":sum(m["total"] for m in months),"archivesWithSetlist":sum(m["with_setlist"] for m in months),
                "performances":total,"uniqueSongs":len(songs),"uniqueArtists":len(ranked),"songs":songs,"artists":ranked,
                "activity":[{"month":m["month_key"],"count":m["activity_count"]} for m in months if m["month_key"] and m["activity_count"]]}
