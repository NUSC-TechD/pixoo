import asyncio
import json

import httpx

from pixoo_server.display.client import PixooClient


def test_tells_pixoo_to_download_hosted_gif() -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"error_code": 0})

    async def scenario() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            await PixooClient(client).play_gif_url(
                "10.42.0.8",
                "http://10.42.0.1/api/screens/makerspace/animation.gif",
            )

    asyncio.run(scenario())

    assert requests == [
        {
            "Command": "Device/PlayTFGif",
            "FileType": 2,
            "FileName": "http://10.42.0.1/api/screens/makerspace/animation.gif",
        }
    ]
