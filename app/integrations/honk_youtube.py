"""Exact official HONK member playlists, never infer from promotional links."""
from pydantic import BaseModel, Field
from app.integrations.youtube_catalog import YouTubeFailure

CHANNEL = 'UCQXuGcIoseWY5HmW6-U7teg'
PLAYLISTS = {
    'moco': 'PLZnoYxfnQoEp-HZLM5r8SMgFnDBmAKHdp',
    'bambi': 'PLZnoYxfnQoErZTpF61YEYdQi2lHsZnLbL',
}


class Membership(BaseModel):
    channel_id: str = Field(pattern=r'^UC[A-Za-z0-9_-]{22}$')
    playlists: dict[str, list[str]]
    basis: str = 'official_member_playlists'


async def collect_memberships(provider):
    out = {}
    for slug, playlist in PLAYLISTS.items():
        ids, token = [], None
        for _ in range(20):
            page = await provider.get('playlistItems', part='snippet,contentDetails', playlistId=playlist,
                                      maxResults=50, **({'pageToken': token} if token else {}))
            for item in page['items']:
                # Require the playlist owner and actual publisher, not a linked guest video.
                if item['snippet'].get('channelId') != CHANNEL or item['snippet'].get('videoOwnerChannelId') != CHANNEL:
                    continue
                ids.append(item['contentDetails']['videoId'])
            token = page.get('nextPageToken')
            if not token:
                break
        if token:
            raise YouTubeFailure('member_playlist_truncated', retry=True, retry_after=3600)
        out[slug] = ids
    return Membership(channel_id=CHANNEL, playlists=out).model_dump()
