"""Check public Shorts URL redirects; no player API, cookies or media downloads."""
from urllib.parse import urlparse, parse_qs
from urllib.robotparser import RobotFileParser


async def robots(client):
    response = await client.get('https://www.youtube.com/robots.txt')
    response.raise_for_status()
    policy = RobotFileParser()
    policy.parse(response.text.splitlines())
    return policy


async def is_short(client, video_id, policy):
    url = f'https://www.youtube.com/shorts/{video_id}'
    if not policy.can_fetch('*', url):
        return None
    response = await client.head(url, follow_redirects=False)
    if response.status_code in (403, 429) or response.status_code >= 500:
        raise RuntimeError('Provider refused format check')
    if response.status_code == 200 and 'text/html' in response.headers.get('content-type', ''):
        return True
    if response.status_code in (301, 302, 303, 307, 308):
        target = urlparse(response.headers.get('location', ''))
        if target.hostname in ('www.youtube.com', 'youtube.com') and target.path == '/watch' and parse_qs(target.query).get('v') == [video_id]:
            return False
    return None
