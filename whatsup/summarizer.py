from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from whatsup.config import OpenRouterConfig
from whatsup.news import NewsArticle

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
APP_TITLE = "WhatsUp Trend News Summaries"


@dataclass(frozen=True)
class SummaryInput:
    """Input payload for one trend summary."""

    trend: str
    search_volume: str
    started: str
    articles: list[NewsArticle]


@dataclass(frozen=True)
class SummaryResult:
    """Structured summary fields for final output."""

    llm_summary: str
    related_us_stock: str
    news_sentiment_score: str


class OpenRouterSummarizer:
    """Summarize trend-related news with OpenRouter."""

    def __init__(
        self,
        api_key: str,
        config: OpenRouterConfig,
        system_prompt: str,
        client: OpenAI | None = None,
    ) -> None:
        self._config = config
        self._system_prompt = system_prompt
        self._client = client or OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key,
            timeout=config.timeout_seconds,
        )

    def summarize(self, summary_input: SummaryInput) -> SummaryResult:
        """Summarize one trend using supplied news articles.

        Args:
            summary_input: Trend metadata and article content.

        Returns:
            Structured LLM summary result.

        Raises:
            OpenAIError: If OpenRouter rejects or cannot complete the request.
            RuntimeError: If OpenRouter returns an empty response.
        """
        user_prompt = _build_user_prompt(summary_input, self._config.summary_word_limit)
        last_error: OpenAIError | RuntimeError | None = None
        for model in self._config.models:
            try:
                return self._summarize_with_model(user_prompt, model)
            except APIStatusError as error:
                last_error = error
                if not _is_model_unavailable_status(error.status_code):
                    raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("OpenRouter summary request exhausted all configured models.")

    def _summarize_with_model(self, user_prompt: str, model: str) -> SummaryResult:
        for attempt_index in range(self._config.max_retries + 1):
            try:
                return self._request_summary(user_prompt, model)
            except APIStatusError as error:
                if _is_model_unavailable_status(error.status_code):
                    raise
                if not _is_retryable_status(error.status_code, attempt_index, self._config.max_retries):
                    raise
                _sleep_before_retry(attempt_index)
            except (RateLimitError, APITimeoutError, APIConnectionError):
                if attempt_index >= self._config.max_retries:
                    raise
                _sleep_before_retry(attempt_index)

        raise RuntimeError(f"OpenRouter summary request exhausted retries for {model}.")

    def _request_summary(self, user_prompt: str, model: str) -> SummaryResult:
        response = self._client.chat.completions.create(
            extra_headers={"X-OpenRouter-Title": APP_TITLE},
            model=model,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("OpenRouter returned an empty summary.")
        return parse_summary_response(content.strip())


def format_summary_error(error: OpenAIError | RuntimeError) -> SummaryResult:
    """Return a user-facing fallback summary for failed LLM requests."""
    return SummaryResult(
        llm_summary=f"Summary unavailable: {error}",
        related_us_stock="",
        news_sentiment_score="",
    )


def parse_summary_response(content: str) -> SummaryResult:
    """Parse the LLM JSON response into final output fields."""
    try:
        payload = json.loads(_extract_json_object(content))
    except json.JSONDecodeError:
        return SummaryResult(
            llm_summary=content,
            related_us_stock="",
            news_sentiment_score="",
        )

    return SummaryResult(
        llm_summary=str(payload.get("llm_summary", "")).strip(),
        related_us_stock=_normalize_stock_tickers(payload.get("related_us_stock", "")),
        news_sentiment_score=_normalize_sentiment_score(
            payload.get("news_sentiment_score", "")
        ),
    )


def _build_user_prompt(summary_input: SummaryInput, word_limit: int) -> str:
    article_sections = []
    for index, article in enumerate(summary_input.articles, start=1):
        article_sections.append(
            "\n".join(
                [
                    f"Article {index}",
                    f"Title: {article.title}",
                    f"Source: {article.source or 'Unknown'}",
                    f"Published: {article.published or 'Unknown'}",
                    f"URL: {article.url}",
                    "Content:",
                    article.content,
                ]
            )
        )

    if not article_sections:
        article_sections.append("No recent Google News RSS articles were found.")

    return "\n\n".join(
        [
            f"Trend: {summary_input.trend}",
            f"Search volume: {summary_input.search_volume}",
            f"Started: {summary_input.started}",
            f"Word limit: {word_limit}",
            "Return valid JSON only with these keys:",
            "- llm_summary: string",
            "- related_us_stock: comma-separated US stock tickers such as AAPL,COST, or an empty string",
            "- news_sentiment_score: integer from 1 to 10, where 1 is very negative and 10 is very positive",
            "News sources:",
            *article_sections,
        ]
    )


def _is_retryable_status(status_code: int, attempt_index: int, max_retries: int) -> bool:
    if attempt_index >= max_retries:
        return False
    return status_code == 429 or status_code >= 500


def _is_model_unavailable_status(status_code: int) -> bool:
    return status_code in {403, 404}


def _sleep_before_retry(attempt_index: int) -> None:
    time.sleep(min(2**attempt_index, 8))


def _extract_json_object(content: str) -> str:
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        return match.group(0)
    return content


def _normalize_stock_tickers(value: object) -> str:
    if isinstance(value, list):
        tickers = [str(item).strip().upper() for item in value]
    else:
        tickers = [ticker.strip().upper() for ticker in str(value).split(",")]

    valid_tickers = [
        ticker
        for ticker in tickers
        if ticker and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", ticker)
    ]
    return ",".join(dict.fromkeys(valid_tickers))


def _normalize_sentiment_score(value: object) -> str:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return ""

    if 1 <= score <= 10:
        return str(score)
    return ""
