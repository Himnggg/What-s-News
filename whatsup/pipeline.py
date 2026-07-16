from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd
from openai import OpenAIError

from whatsup.config import AppConfig
from whatsup.news import NewsArticle, get_top_news_articles
from whatsup.summarizer import (
    OpenRouterSummarizer,
    SummaryResult,
    SummaryInput,
    format_summary_error,
)
from whatsup.trends import (
    SEARCH_VOLUME_COLUMN,
    STARTED_COLUMN,
    TREND_COLUMN,
    fetch_trends,
    select_top_trends,
)

SUMMARY_COLUMN = "LLM summary"
RELATED_US_STOCK_COLUMN = "Related US stock"
NEWS_SENTIMENT_SCORE_COLUMN = "News sentiment score"
FINAL_COLUMNS = [
    TREND_COLUMN,
    SEARCH_VOLUME_COLUMN,
    STARTED_COLUMN,
    SUMMARY_COLUMN,
    RELATED_US_STOCK_COLUMN,
    NEWS_SENTIMENT_SCORE_COLUMN,
]
NewsFetcher = Callable[[str], list[NewsArticle]]
TrendFetcher = Callable[[], pd.DataFrame]


def run_pipeline(
    config: AppConfig,
    summarizer: OpenRouterSummarizer,
    trend_fetcher: TrendFetcher | None = None,
    news_fetcher: NewsFetcher | None = None,
) -> pd.DataFrame:
    """Run the full trend-news-summary pipeline.

    Args:
        config: Application configuration.
        summarizer: OpenRouter summarizer.
        trend_fetcher: Optional trend fetcher for tests.
        news_fetcher: Optional news fetcher for tests.

    Returns:
        DataFrame with exactly 20 configured summary rows and final columns.
    """
    fetch_trend_records = trend_fetcher or (lambda: fetch_trends(config.trends))
    fetch_news = news_fetcher or (
        lambda trend: get_top_news_articles(trend, config.news)
    )

    raw_trends = fetch_trend_records()
    top_trends = select_top_trends(raw_trends, config.trends.top_n)
    articles_by_trend = _fetch_news_for_trends(top_trends, fetch_news, config.news.max_workers)
    return _summarize_trends(top_trends, articles_by_trend, summarizer)


def write_output_csv(results: pd.DataFrame, output_dir: Path) -> Path:
    """Write final summary results to a timestamped CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = output_dir / f"trend_news_summary_{timestamp}.csv"
    results.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def _fetch_news_for_trends(
    top_trends: pd.DataFrame,
    news_fetcher: NewsFetcher,
    max_workers: int,
) -> dict[str, list[NewsArticle]]:
    articles_by_trend: dict[str, list[NewsArticle]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_trend = {
            executor.submit(news_fetcher, str(row[TREND_COLUMN])): str(row[TREND_COLUMN])
            for _, row in top_trends.iterrows()
        }
        for future in as_completed(future_to_trend):
            trend = future_to_trend[future]
            try:
                articles_by_trend[trend] = future.result()
            except (OSError, RuntimeError, ValueError, TypeError):
                articles_by_trend[trend] = []

    return articles_by_trend


def _summarize_trends(
    top_trends: pd.DataFrame,
    articles_by_trend: dict[str, list[NewsArticle]],
    summarizer: OpenRouterSummarizer,
) -> pd.DataFrame:
    result_rows: list[dict[str, str]] = []
    for _, row in top_trends.iterrows():
        trend = str(row[TREND_COLUMN])
        articles = articles_by_trend.get(trend, [])
        summary_result = _summarize_trend(row, articles, summarizer)
        result_rows.append(
            {
                TREND_COLUMN: trend,
                SEARCH_VOLUME_COLUMN: str(row[SEARCH_VOLUME_COLUMN]),
                STARTED_COLUMN: str(row[STARTED_COLUMN]),
                SUMMARY_COLUMN: summary_result.llm_summary,
                RELATED_US_STOCK_COLUMN: summary_result.related_us_stock,
                NEWS_SENTIMENT_SCORE_COLUMN: summary_result.news_sentiment_score,
            }
        )

    return pd.DataFrame(result_rows, columns=FINAL_COLUMNS)


def _summarize_trend(
    trend_row: pd.Series,
    articles: list[NewsArticle],
    summarizer: OpenRouterSummarizer,
) -> SummaryResult:
    if not articles:
        return SummaryResult(
            llm_summary="Summary unavailable: no recent Google News RSS articles were found.",
            related_us_stock="",
            news_sentiment_score="",
        )

    summary_input = SummaryInput(
        trend=str(trend_row[TREND_COLUMN]),
        search_volume=str(trend_row[SEARCH_VOLUME_COLUMN]),
        started=str(trend_row[STARTED_COLUMN]),
        articles=articles,
    )
    try:
        return summarizer.summarize(summary_input)
    except (OpenAIError, RuntimeError) as error:
        return format_summary_error(error)
