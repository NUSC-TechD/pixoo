from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import api_router
from .cloud_emulator.routes import cloud_router
from .cloud_emulator.state import DeviceStore
from .config.settings import Settings
from .display.scheduler import DisplayScheduler
from .mqtt.broker import MqttBroker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None, *, enable_services: bool = True) -> FastAPI:
    config = settings or Settings.load()
    devices = DeviceStore()
    broker = MqttBroker(config.mqtt_port, devices)
    scheduler = DisplayScheduler(
        config.screens,
        config.api_key,
        media_base_url=f"http://{config.host_ip}:{config.http_port}",
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.scheduler = scheduler
        if enable_services:
            await broker.start()
            await scheduler.start()
        yield
        if enable_services:
            await scheduler.stop()
            await broker.stop()

    app = FastAPI(
        title="NUSC Pixoo Server",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.devices = devices
    app.state.scheduler = scheduler
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(cloud_router(config, devices))
    app.include_router(api_router())
    return app


app = create_app()


def main() -> None:
    """Run the FastAPI application with its configured HTTP port."""
    uvicorn.run(app, host="0.0.0.0", port=app.state.settings.http_port)


if __name__ == "__main__":
    main()
