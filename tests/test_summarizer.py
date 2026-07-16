from types import SimpleNamespace

import httpx
from openai import APITimeoutError

from whatsup.config import OpenRouterConfig
from whatsup.news import NewsArticle
from whatsup.summarizer import OpenRouterSummarizer, SummaryInput, parse_summary_response


class FakeCompletions:
    def __init__(self) -> None:
        self.call_count = 0

    def create(self, **kwargs):
        self.call_count += 1
        if self.call_count == 1:
            request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
            raise APITimeoutError(request=request)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"llm_summary": "The topic is trending because of recent news.", '
                            '"related_us_stock": "AAPL,COST", '
                            '"news_sentiment_score": 7}'
                        )
                    )
                )
            ]
        )


class FakeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions())


def test_summarizer_retries_transient_timeout(monkeypatch) -> None:
    monkeypatch.setattr("whatsup.summarizer.time.sleep", lambda seconds: None)
    config = OpenRouterConfig(
        model="google/gemini-3.5-flash",
        fallback_models=(),
        timeout_seconds=10,
        max_retries=1,
        summary_word_limit=120,
        prompt_path=SimpleNamespace(),
    )
    client = FakeClient()
    summarizer = OpenRouterSummarizer(
        api_key="test-key",
        config=config,
        system_prompt="Summarize factually.",
        client=client,
    )
    summary_input = SummaryInput(
        trend="example",
        search_volume="1M+",
        started="July 16, 2026",
        articles=[
            NewsArticle(
                title="Story",
                source="Example News",
                published="Thu, 16 Jul 2026 01:00:00 GMT",
                url="https://example.com/story",
                content="Article content",
            )
        ],
    )

    summary_result = summarizer.summarize(summary_input)

    assert summary_result.llm_summary == "The topic is trending because of recent news."
    assert summary_result.related_us_stock == "AAPL,COST"
    assert summary_result.news_sentiment_score == "7"
    assert client.chat.completions.call_count == 2


def test_parse_summary_response_handles_markdown_wrapped_json() -> None:
    result = parse_summary_response(
        '```json\n{"llm_summary": "Summary", "related_us_stock": ["aapl", "COST"], '
        '"news_sentiment_score": "10"}\n```'
    )

    assert result.llm_summary == "Summary"
    assert result.related_us_stock == "AAPL,COST"
    assert result.news_sentiment_score == "10"
