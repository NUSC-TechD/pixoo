"""HTTP routes for inspecting and controlling configured Pixoo devices."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response

logger = logging.getLogger(__name__)


def api_router() -> APIRouter:
    """Build the operator-facing API router."""
    router = APIRouter(prefix="/api")

    @router.get("/screens")
    async def screens(request: Request) -> list[dict[str, object]]:
        return request.app.state.scheduler.snapshot()

    @router.get("/screens/{name}/animation.gif")
    async def animation(name: str, request: Request) -> Response:
        content = request.app.state.scheduler.animation(name)
        if content is None:
            raise HTTPException(status_code=404, detail=f"No animation available for: {name}")
        return Response(
            content=content,
            media_type="image/gif",
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/screens/{name}/refresh")
    async def refresh(name: str, request: Request) -> dict[str, str]:
        try:
            await request.app.state.scheduler.refresh(name)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=f"Unknown screen: {name}") from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except Exception as error:
            logger.exception("Manual screen update failed: %s", name)
            raise HTTPException(status_code=502, detail=str(error)) from error
        return {"status": "updated", "screen": name}

    return router
