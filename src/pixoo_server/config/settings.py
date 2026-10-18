"""Validated settings loaded from arguments, environment, dotenv, and TOML."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from .models import PixooConfig


class Settings(BaseSettings):
    """Represent the application's complete, validated configuration.

    Settings combines server values and all physical screen definitions. It
    applies Pydantic's validation after merging constructor arguments,
    environment variables, ``.env``, the selected TOML file, and secret-file
    values in that precedence order.
    """

    model_config = SettingsConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        env_file=".env",
        env_ignore_empty=True,
        toml_file="pixoo.toml",
    )

    host_ip: str = Field(
        default="10.42.0.1",
        min_length=1,
        validation_alias="PIXOOPAL_HOST_IP",
    )
    public_ip: str = Field(
        default="80.92.211.126",
        min_length=1,
        validation_alias="PUBLIC_IP",
    )
    device_id: int = Field(default=12345, gt=0, validation_alias="PIXOO_DEVICE_ID")
    http_port: int = Field(default=80, ge=1, le=65535, validation_alias="HTTP_PORT")
    mqtt_port: int = Field(default=1883, ge=1, le=65535, validation_alias="MQTT_PORT")
    api_key: str | None = Field(default=None, validation_alias="DATA_GOV_SG_API_KEY")
    bus_api_base_url: str = Field(
        default="https://bus.hewliyang.com/api/stop",
        min_length=1,
        validation_alias="NUS_BUS_API_BASE_URL",
    )
    screens: tuple[PixooConfig, ...] = ()

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> Settings:
        path = Path(config_path or os.getenv("PIXOO_CONFIG", "pixoo.toml"))
        configured_type = type(
            "ConfiguredSettings",
            (cls,),
            {"model_config": {**cls.model_config, "toml_file": path}},
        )
        return configured_type()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    @field_validator("host_ip", "public_ip", "api_key", "bus_api_base_url")
    @classmethod
    def strip_strings(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @model_validator(mode="after")
    def unique_screens(self) -> Self:
        names = [screen.name for screen in self.screens]
        if len(names) != len(set(names)):
            raise ValueError("Screen names must be unique")
        return self
