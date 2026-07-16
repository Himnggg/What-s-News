from pathlib import Path

import pandas as pd
import pytest

from whatsup.telegram import (
    TelegramConfig,
    build_summary_messages,
    load_telegram_config,
    send_summary_to_telegram,
)


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"ok": True}


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def post(self, url, data):
        self.calls.append({"url": url, "data": data})
        return FakeResponse()


def test_load_telegram_config_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")

    config = load_telegram_config()

    assert config.bot_token == "token"
    assert config.chat_id == "chat"


def test_load_telegram_config_requires_env(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        load_telegram_config()


def test_build_summary_messages_formats_rows(tmp_path) -> None:
    output_path = tmp_path / "summary.csv"
    results = _summary_dataframe()

    messages = build_summary_messages(results, output_path)

    assert messages
    assert "<b>Google Trend News Summary</b>" in messages[0]
    assert "<b>1. example trend</b>" in messages[0]
    assert "Volume: <code>100K+</code> | Sentiment: <b>8/10</b>" in messages[0]
    assert "Stock: <code>AAPL,COST</code>" in messages[0]
    assert "Summary: Example summary" in messages[0]


def test_send_summary_to_telegram_sends_formatted_messages(monkeypatch, tmp_path) -> None:
    output_path = tmp_path / "summary.csv"
    output_path.write_text("Trends,LLM summary\nexample,summary\n", encoding="utf-8")
    fake_client = FakeClient()
    results = _summary_dataframe()

    monkeypatch.setattr("whatsup.telegram.httpx.Client", lambda timeout: fake_client)

    send_summary_to_telegram(
        TelegramConfig(bot_token="token", chat_id="chat"),
        results,
        output_path,
    )

    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["data"]["text"].startswith("<b>Google Trend News Summary</b>")
    assert fake_client.calls[0]["data"]["parse_mode"] == "HTML"


def _summary_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Trends": "example trend",
                "Search volume": "100K+",
                "Started": "July 16, 2026 at 1:00:00 AM UTC+8",
                "LLM summary": "Example summary",
                "Related US stock": "AAPL,COST",
                "News sentiment score": "8",
            }
        ]
    )
