# comic_demo/configuration_utils.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Optional, Literal, List
import time

import tomllib

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    computed_field,
    field_validator,
)


def _resolve_relative_path_to_config_dir(v: Path, info: ValidationInfo) -> Path:
    """
    Resolve relative paths based on config.toml's directory (not cwd).

    Requires the caller to pass config_dir in model_validate(..., context={"config_dir": <Path|str>}).
    """
    ctx = info.context or {}
    base = ctx.get("config_dir")
    if not base:
        return v

    v2 = v.expanduser()
    if v2.is_absolute():
        return v2

    base_dir = Path(base).expanduser()
    return (base_dir / v2).resolve(strict=False)


def _resolve_paths_recursively(value: Any, info: ValidationInfo) -> Any:
    """
    Recursively process Path objects in container types (list/tuple/set/dict).
    """
    if value is None:
        return None

    if isinstance(value, Path):
        return _resolve_relative_path_to_config_dir(value, info)

    if isinstance(value, list):
        return [_resolve_paths_recursively(v, info) for v in value]

    if isinstance(value, tuple):
        return tuple(_resolve_paths_recursively(v, info) for v in value)

    if isinstance(value, set):
        return {_resolve_paths_recursively(v, info) for v in value}

    if isinstance(value, dict):
        return {k: _resolve_paths_recursively(v, info) for k, v in value.items()}

    return value


class ConfigBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def _resolve_all_path_fields(cls, v: Any, info: ValidationInfo) -> Any:
        # Allow explicitly disabling path resolution for specific fields:
        # Field(..., json_schema_extra={"resolve_relative": False})
        if info.field_name:
            field = cls.model_fields.get(info.field_name)
            extra = (field.json_schema_extra or {}) if field else {}
            if extra.get("resolve_relative") is False:
                return v

        return _resolve_paths_recursively(v, info)


class DeveloperConfig(ConfigBaseModel):
    developer_mode: bool = False
    default_llm: str = "deepseek-chat"
    default_image_llm: str = "seedream-5.0"
    default_video_llm: str = "seedance-1.5"
    chat_models_config: dict[str, dict[str, Any]] = Field(default_factory=dict)
    print_context: bool = False


class ProjectConfig(ConfigBaseModel):
    media_dir: Path = Field(
        ..., description="Media directory for input videos and images"
    )
    bgm_dir: Path = Field(..., description="Background music (BGM) directory")
    outputs_dir: Path = Field(..., description="Output directory")

    @computed_field(return_type=Path)
    @property
    def blobs_dir(self) -> Path:
        return self.outputs_dir


class LLMConfig(ConfigBaseModel):
    model: str
    base_url: str
    api_key: str
    timeout: float = 30.0
    temperature: Optional[float] = None
    max_retries: int = 2


class ImageLLMConfig(ConfigBaseModel):
    model: str
    base_url: str = ""
    api_key: str = ""
    timeout: float = 60.0
    max_retries: int = 2


class VideoLLMConfig(ConfigBaseModel):
    model: str
    base_url: str = ""
    api_key: str = ""
    timeout: float = 120.0
    max_retries: int = 2


class MCPConfig(ConfigBaseModel):
    server_name: str = "comic_demo"
    server_cache_dir: str = "./comic_demo/.server_cache"
    server_transport: Literal["stdio", "sse", "streamable-http"] = "streamable-http"
    url_scheme: str = "http"
    connect_host: str = "127.0.0.1"
    port: int = Field(ge=1, le=65535)
    path: str = "/mcp"

    json_response: bool = True
    stateless_http: bool = False

    timeout: int = 600

    available_node_pkgs: List[str] = []
    available_nodes: List[str] = []

    @property
    def url(self) -> str:
        return f"{self.url_scheme}://{self.connect_host}:{self.port}{self.path}"


class SkillsConfig(ConfigBaseModel):
    skill_dir: Path = Field(..., description="Skill directory.")


class Settings(ConfigBaseModel):
    developer: DeveloperConfig
    project: ProjectConfig

    llm: LLMConfig
    image_llm: ImageLLMConfig = Field(
        default_factory=lambda: ImageLLMConfig(model="seedream-5.0")
    )
    video_llm: VideoLLMConfig = Field(
        default_factory=lambda: VideoLLMConfig(model="seedance-1.5")
    )

    local_mcp_server: MCPConfig

    skills: SkillsConfig


def load_settings(config_path: str | Path) -> Settings:
    p = Path(config_path).expanduser().resolve()
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    return Settings.model_validate(data, context={"config_dir": p.parent})


def default_config_path() -> str:
    return os.getenv("COMICDEMO_CONFIG", "config.toml")
