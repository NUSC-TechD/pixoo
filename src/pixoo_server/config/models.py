"""Validated configuration models for screens and their views."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ViewConfig(BaseModel):
    """Describe one content item in a screen's playlist.

    A view selects a content screen (currently ``haze``), controls how long its
    frames remain visible, and holds screen-specific options such as the PSI
    region. It does not identify a physical Pixoo; that is the responsibility
    of :class:`PixooConfig`.
    """

    model_config = ConfigDict(extra="allow")

    type: Literal["haze"]
    duration_seconds: int = Field(default=10, ge=1, le=30)

    @property
    def options(self) -> dict[str, Any]:
        return self.model_dump(exclude={"type", "duration_seconds"})


class PixooConfig(BaseModel):
    """Describe one physical Pixoo and the playlist delivered to it.

    A screen owns the device's network address and refresh cadence. Its nested
    :class:`ViewConfig` entries describe the content rendered and combined into
    that screen's animation. Cloud bootstrap identity is global server config,
    not a property of an individual screen.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    address: str = Field(min_length=1)
    refresh_seconds: int = Field(default=900, ge=60)
    views: list[ViewConfig] = Field(min_length=1)
