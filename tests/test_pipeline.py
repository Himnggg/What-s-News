from pathlib import Path

import pandas as pd

from whatsup.config import AppConfig, NewsConfig, OpenRouterConfig, OutputConfig, TrendsConfig
from whatsup.news import NewsArticle
from whatsup.pipeline import FINAL_COLUMNS, run_pipeline
from whatsup.summarizer import SummaryResult


class FakeSummarizer:
    def summarize(self, summary_input) -> SummaryResult:
        return SummaryResult(
            llm_summary=f"Summary for {summary_input.trend}",
            related_us_stock="AAPL,COST",
            news_sentiment_score="8",
        )


def _app_config() -> AppConfig:
    return AppConfig(
        trends=TrendsConfig(
            country_code="US",
            window_hours=24,
            top_n=20,
            download_dir=Path("downloads"),
        ),
        news=NewsConfig(
            top_n=3,
            locale_hl="en-US",
            locale_gl="US",
            locale_ceid="US:en",
            request_timeout_seconds=5,
            max_article_chars=500,
            max_workers=2,
        ),
        openrouter=OpenRouterConfig(
            model="google/gemini-3.5-flash",
            fallback_models=("z-ai/glm-5.2",),
            timeout_seconds=10,
            max_retries=1,
            summary_word_limit=120,
            prompt_path=Path("prompt.txt"),
        ),
        output=OutputConfig(output_dir=Path("outputs")),
    )


def test_run_pipeline_returns_twenty_rows_and_expected_columns() -> None:
    trend_records = pd.DataFrame(
        {
            "Trends": [f"trend {index}" for index in range(21)],
            "Search volume": [f"{index + 1}K+" for index in range(21)],
            "Started": [f"July 16, 2026 at {index % 12 + 1}:00:00 AM UTC+8" for index in range(21)],
        }
    )

    def fake_news_fetcher(trend: str) -> list[NewsArticle]:
        return [
            NewsArticle(
                title=f"{trend} story",
                source="Example News",
                published="Thu, 16 Jul 2026 01:00:00 GMT",
                url="https://example.com/story",
                content="Article content",
            )
        ]

    results = run_pipeline(
        _app_config(),
        FakeSummarizer(),
        trend_fetcher=lambda: trend_records,
        news_fetcher=fake_news_fetcher,
    )

    assert len(results) == 20
    assert results.columns.tolist() == FINAL_COLUMNS
    assert results.iloc[0]["Trends"] == "trend 20"
    assert results.iloc[0]["Related US stock"] == "AAPL,COST"
    assert results.iloc[0]["News sentiment score"] == "8"
