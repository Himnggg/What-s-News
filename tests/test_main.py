from pathlib import Path

import main
from whatsup.config import AppConfig, NewsConfig, OpenRouterConfig, OutputConfig, TrendsConfig


def _app_config() -> AppConfig:
    return AppConfig(
        trends=TrendsConfig(
            country_code="US",
            window_hours=24,
            top_n=40,
            download_dir=Path("downloads"),
        ),
        news=NewsConfig(
            top_n=3,
            locale_hl="en-US",
            locale_gl="US",
            locale_ceid="US:en",
            request_timeout_seconds=15,
            max_article_chars=6000,
            max_workers=4,
        ),
        openrouter=OpenRouterConfig(
            model="google/gemini-3.5-flash",
            fallback_models=("z-ai/glm-5.2",),
            timeout_seconds=60,
            max_retries=2,
            summary_word_limit=120,
            prompt_path=Path("prompts/news-summary.txt"),
        ),
        output=OutputConfig(output_dir=Path("outputs")),
    )


def test_load_config_with_overrides_updates_trends_only(monkeypatch) -> None:
    config = _app_config()
    monkeypatch.setattr(main, "load_config", lambda: config)

    args = main.parse_args(["--window-hours", "4", "--top-n", "30"])

    result = main.load_config_with_overrides(args)

    assert result.trends.window_hours == 4
    assert result.trends.top_n == 30
    assert result.news == config.news
    assert result.openrouter == config.openrouter
    assert result.output == config.output


def test_parse_args_rejects_non_positive_values() -> None:
    try:
        main.parse_args(["--window-hours", "0"])
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("Expected argparse to reject non-positive window hours")
