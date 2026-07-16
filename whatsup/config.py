from __future__ import annotations

import os
import tomllib  # type: ignore[import-not-found]
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.toml"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class TrendsConfig:
    """Configuration for Google Trends retrieval and ranking."""

    country_code: str
    window_hours: int
    top_n: int
    download_dir: Path


@dataclass(frozen=True)
class NewsConfig:
    """Configuration for Google News RSS and article extraction."""

    top_n: int
    locale_hl: str
    locale_gl: str
    locale_ceid: str
    request_timeout_seconds: int
    max_article_chars: int
    max_workers: int


@dataclass(frozen=True)
class OpenRouterConfig:
    """Configuration for OpenRouter summarization."""

    model: str
    fallback_models: tuple[str, ...]
    timeout_seconds: int
    max_retries: int
    summary_word_limit: int
    prompt_path: Path

    @property
    def models(self) -> tuple[str, ...]:
        """Return primary and fallback models in attempt order."""
        return (self.model, *self.fallback_models)


@dataclass(frozen=True)
class OutputConfig:
    """Configuration for generated output files."""

    output_dir: Path


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    trends: TrendsConfig
    news: NewsConfig
    openrouter: OpenRouterConfig
    output: OutputConfig


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Load application configuration from TOML.

    Args:
        config_path: Path to the TOML configuration file.

    Returns:
        Parsed application configuration.

    Raises:
        FileNotFoundError: If the config file does not exist.
        KeyError: If a required config section or key is missing.
    """
    with config_path.open("rb") as config_file:
        raw_config = tomllib.load(config_file)

    return AppConfig(
        trends=_load_trends_config(raw_config["trends"]),
        news=_load_news_config(raw_config["news"]),
        openrouter=_load_openrouter_config(raw_config["openrouter"]),
        output=_load_output_config(raw_config["output"]),
    )


def load_env_file(env_path: Path = DEFAULT_ENV_PATH) -> None:
    """Load missing environment variables from a local .env file.

    Args:
        env_path: Path to a KEY=VALUE env file.
    """
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#") or "=" not in stripped_line:
            continue
        key, _, value = stripped_line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def load_system_prompt(prompt_path: Path) -> str:
    """Read the OpenRouter system prompt text.

    Args:
        prompt_path: Path to the prompt text file.

    Returns:
        Prompt content without surrounding whitespace.

    Raises:
        ValueError: If the prompt file is empty.
    """
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"Prompt file is empty: {prompt_path}")
    return prompt


def get_openrouter_api_key() -> str:
    """Return the OpenRouter API key from the environment.

    Returns:
        The configured OpenRouter API key.

    Raises:
        RuntimeError: If OPENROUTER_API_KEY is not set.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Set OPENROUTER_API_KEY before running the pipeline.")
    return api_key


def _load_trends_config(raw_config: dict[str, Any]) -> TrendsConfig:
    return TrendsConfig(
        country_code=str(raw_config["country_code"]),
        window_hours=int(raw_config["window_hours"]),
        top_n=int(raw_config["top_n"]),
        download_dir=_resolve_project_path(str(raw_config["download_dir"])),
    )


def _load_news_config(raw_config: dict[str, Any]) -> NewsConfig:
    return NewsConfig(
        top_n=int(raw_config["top_n"]),
        locale_hl=str(raw_config["locale_hl"]),
        locale_gl=str(raw_config["locale_gl"]),
        locale_ceid=str(raw_config["locale_ceid"]),
        request_timeout_seconds=int(raw_config["request_timeout_seconds"]),
        max_article_chars=int(raw_config["max_article_chars"]),
        max_workers=int(raw_config["max_workers"]),
    )


def _load_openrouter_config(raw_config: dict[str, Any]) -> OpenRouterConfig:
    return OpenRouterConfig(
        model=str(raw_config["model"]),
        fallback_models=tuple(str(model) for model in raw_config.get("fallback_models", [])),
        timeout_seconds=int(raw_config["timeout_seconds"]),
        max_retries=int(raw_config["max_retries"]),
        summary_word_limit=int(raw_config["summary_word_limit"]),
        prompt_path=_resolve_project_path(str(raw_config["prompt_path"])),
    )


def _load_output_config(raw_config: dict[str, Any]) -> OutputConfig:
    return OutputConfig(output_dir=_resolve_project_path(str(raw_config["output_dir"])))


def _resolve_project_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path
