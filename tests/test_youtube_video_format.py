import asyncio
from urllib.robotparser import RobotFileParser
import httpx
from app.integrations.youtube_video_format import is_short


def test_public_short_url_classification_and_unknown_responses():
    policy=RobotFileParser(); policy.parse(['User-agent: *','Allow: /'])
    def respond(request):
        key=request.url.path.rsplit('/',1)[-1]
        if key=='shortvideo1':return httpx.Response(200,headers={'content-type':'text/html'})
        if key=='normalvideo':return httpx.Response(303,headers={'location':'https://www.youtube.com/watch?v=normalvideo'})
        return httpx.Response(302,headers={'location':'https://consent.youtube.com/'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            assert await is_short(client,'shortvideo1',policy) is True
            assert await is_short(client,'normalvideo',policy) is False
            assert await is_short(client,'unknownclip',policy) is None
    asyncio.run(run())


def test_disallowed_url_never_starts_request():
    policy=RobotFileParser();policy.parse(['User-agent: *','Disallow: /shorts/'])
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: (_ for _ in ()).throw(AssertionError('network')))) as client:
            assert await is_short(client,'shortvideo1',policy) is None
    asyncio.run(run())
