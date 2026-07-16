from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from whatsup.config import (
    AppConfig,
    get_openrouter_api_key,
    load_config,
    load_env_file,
    load_system_prompt,
)
from whatsup.pipeline import run_pipeline, write_output_csv
from whatsup.summarizer import OpenRouterSummarizer
from whatsup.telegram import load_telegram_config, send_summary_to_telegram


def main(argv: list[str] | None = None) -> None:
    """Run the Google Trend news summary pipeline."""
    args = parse_args(argv)
    load_env_file()
    config = load_config_with_overrides(args)
    api_key = get_openrouter_api_key()
    telegram_config = load_telegram_config()
    system_prompt = load_system_prompt(config.openrouter.prompt_path)
    summarizer = OpenRouterSummarizer(
        api_key=api_key,
        config=config.openrouter,
        system_prompt=system_prompt,
    )
    results = run_pipeline(config, summarizer)
    output_path = write_output_csv(results, config.output.output_dir)
    print(f"Wrote {len(results)} trend summaries to {output_path}")
    send_summary_to_telegram(telegram_config, results, output_path)
    print("Telegram summary sent OK")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the pipeline runner."""
    parser = argparse.ArgumentParser(
        description="Run the Google Trend news summary pipeline.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to the TOML config file. Defaults to config.toml.",
    )
    parser.add_argument(
        "--window-hours",
        type=_positive_int,
        default=None,
        help="Override trends.window_hours from config.toml.",
    )
    parser.add_argument(
        "--top-n",
        type=_positive_int,
        default=None,
        help="Override trends.top_n from config.toml.",
    )
    return parser.parse_args(argv)


def load_config_with_overrides(args: argparse.Namespace) -> AppConfig:
    """Load config and apply optional CLI overrides."""
    config = load_config(args.config) if args.config else load_config()
    if args.window_hours is None and args.top_n is None:
        return config

    return replace(
        config,
        trends=replace(
            config.trends,
            window_hours=args.window_hours or config.trends.window_hours,
            top_n=args.top_n or config.trends.top_n,
        ),
    )


def _positive_int(value: str) -> int:
    try:
        parsed_value = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{value!r} must be an integer.") from error

    if parsed_value <= 0:
        raise argparse.ArgumentTypeError(f"{value!r} must be greater than 0.")
    return parsed_value


if __name__ == "__main__":
    main()
