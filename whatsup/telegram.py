from __future__ import annotations

import html
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
import pandas as pd

TELEGRAM_API_BASE_URL = "https://api.telegram.org"
TELEGRAM_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "TELEGRAM_CHAT_ID"
DEFAULT_TIMEOUT_SECONDS = 30
MAX_TELEGRAM_MESSAGE_LENGTH = 3900


@dataclass(frozen=True)
class TelegramConfig:
    """Telegram bot configuration from environment variables."""

    bot_token: str
    chat_id: str
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


def load_telegram_config() -> TelegramConfig:
    """Load Telegram credentials from environment variables.

    Returns:
        Telegram bot configuration.

    Raises:
        RuntimeError: If token or chat id is missing.
    """
    bot_token = os.getenv(TELEGRAM_BOT_TOKEN_ENV, "").strip()
    chat_id = os.getenv(TELEGRAM_CHAT_ID_ENV, "").strip()
    if not bot_token or not chat_id:
        raise RuntimeError(
            f"Set {TELEGRAM_BOT_TOKEN_ENV} and {TELEGRAM_CHAT_ID_ENV} before sending Telegram messages."
        )
    return TelegramConfig(bot_token=bot_token, chat_id=chat_id)


def send_summary_to_telegram(
    config: TelegramConfig,
    results: pd.DataFrame,
    output_path: Path,
) -> None:
    """Send formatted trend summaries to a Telegram chat.

    Args:
        config: Telegram bot configuration.
        results: Final summary DataFrame.
        output_path: Path to the generated CSV summary.

    Raises:
        FileNotFoundError: If the output CSV does not exist.
        RuntimeError: If Telegram returns an unsuccessful response.
        httpx.HTTPError: If the request fails.
    """
    if not output_path.exists():
        raise FileNotFoundError(f"Summary CSV not found: {output_path}")

    messages = build_summary_messages(results, output_path)
    with httpx.Client(timeout=config.timeout_seconds) as client:
        for message in messages:
            _post_telegram(
                client,
                config,
                "sendMessage",
                data={
                    "chat_id": config.chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": "true",
                },
            )


def build_summary_messages(results: pd.DataFrame, output_path: Path) -> list[str]:
    """Format all summary rows into Telegram-safe HTML messages."""
    header = _build_summary_header(output_path, len(results))
    row_blocks = [
        _build_summary_row(index=index, row=row)
        for index, (_, row) in enumerate(results.iterrows(), start=1)
    ]
    messages = _split_message_blocks(header, row_blocks)
    total_parts = len(messages)
    if total_parts == 1:
        return messages
    return [
        f"{message}\n\nPart {index}/{total_parts}"
        for index, message in enumerate(messages, start=1)
    ]


def _build_summary_header(output_path: Path, row_count: int) -> str:
    return (
        "<b>Google Trend News Summary</b>\n"
        f"Rows: {row_count}\n"
        f"CSV saved: <code>{html.escape(output_path.name)}</code>"
    )


def _build_summary_row(index: int, row: pd.Series) -> str:
    trend = _escape_value(row.get("Trends", ""))
    search_volume = _escape_value(row.get("Search volume", ""))
    started = _escape_value(row.get("Started", ""))
    summary = _escape_value(row.get("LLM summary", ""))
    related_stock = _escape_value(row.get("Related US stock", "")) or "-"
    sentiment = _escape_value(row.get("News sentiment score", "")) or "-"
    return "\n".join(
        [
            f"<b>{index}. {trend}</b>",
            f"Volume: <code>{search_volume}</code> | Sentiment: <b>{sentiment}/10</b>",
            f"Stock: <code>{related_stock}</code>",
            f"Started: {started}",
            f"Summary: {summary}",
        ]
    )


def _split_message_blocks(header: str, row_blocks: list[str]) -> list[str]:
    messages: list[str] = []
    current_message = header
    for row_block in row_blocks:
        candidate = f"{current_message}\n\n{row_block}"
        if len(candidate) <= MAX_TELEGRAM_MESSAGE_LENGTH:
            current_message = candidate
            continue

        messages.append(current_message)
        current_message = f"{header}\n\n{_truncate_block(row_block)}"

    messages.append(current_message)
    return messages


def _escape_value(value: object) -> str:
    if pd.isna(value):
        return ""
    return html.escape(str(value).strip())


def _truncate_block(row_block: str) -> str:
    max_block_length = MAX_TELEGRAM_MESSAGE_LENGTH - 500
    if len(row_block) <= max_block_length:
        return row_block
    return f"{row_block[:max_block_length]}..."


def _post_telegram(
    client: httpx.Client,
    config: TelegramConfig,
    method: str,
    data: dict[str, str],
) -> None:
    url = f"{TELEGRAM_API_BASE_URL}/bot{config.bot_token}/{method}"
    response = client.post(url, data=data)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        description = payload.get("description", "unknown Telegram API error")
        raise RuntimeError(f"Telegram {method} failed: {description}")
