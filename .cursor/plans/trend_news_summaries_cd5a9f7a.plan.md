---
name: Trend News Summaries
overview: 建立一條可重跑嘅 pipeline：取得美國 24 小時 trends、按可比較嘅 search volume 排序取 Top 20、為每項讀取 Google News RSS Top 3 文章，再經 OpenRouter 產生摘要並輸出固定 20-row DataFrame/CSV。Top 3 會定義為 Google News RSS 排序最前嘅三項，而唔係一般 Google Search 網頁排名。
todos:
  - id: config-deps
    content: Add configuration, prompt, dependencies, and secret validation
    status: completed
  - id: trend-ranking
    content: Implement numeric search-volume sorting and deterministic Top 20 selection
    status: completed
  - id: news-fetch
    content: Implement Google News RSS Top 3 retrieval and article extraction fallbacks
    status: completed
  - id: openrouter-summary
    content: Implement configurable OpenRouter summarization with bounded retries
    status: completed
  - id: pipeline-cli
    content: Assemble the 20-row DataFrame pipeline, CLI, and timestamped CSV output
    status: completed
  - id: tests-docs
    content: Add mocked tests, run smoke verification, and document usage/limitations
    status: completed
isProject: false
---

# Google Trend News Summary Pipeline

## Data flow
```mermaid
flowchart LR
    Trends["Google Trends CSV"] --> Rank["Parse volume and Top 20"]
    Rank --> News["Google News RSS when:1d"]
    News --> Extract["Resolve URLs and extract Top 3 articles"]
    Extract --> LLM["OpenRouter summary"]
    LLM --> Result["20-row DataFrame and output CSV"]
```

## Configuration and dependencies
- Add runtime dependencies in [pyproject.toml](C:/Users/bhke05279/Documents/WhatsUp/pyproject.toml): `feedparser`, `googlenewsdecoder`, `trafilatura`, and the official `openai` client; add `pytest` as a dev dependency.
- Add [config.toml](C:/Users/bhke05279/Documents/WhatsUp/config.toml) with default model `google/gemini-3.5-flash`, Top 20/Top 3 limits, request timeouts, article text cap, and bounded concurrency. Keep the secret exclusively in `OPENROUTER_API_KEY`.
- Add [prompts/news-summary.txt](C:/Users/bhke05279/Documents/WhatsUp/prompts/news-summary.txt) with an English factual-summary prompt: use only supplied sources, explain why the topic is trending, identify uncertainty/conflicts, and stay within 120 words.

## Pipeline modules
- Move trend retrieval/ranking into [whatsup/trends.py](C:/Users/bhke05279/Documents/WhatsUp/whatsup/trends.py): parse values such as `20K+`, `1M+`, and comma-separated numbers into a temporary numeric field; sort descending with `Started` as deterministic tie-breaker; return exactly 20 rows while preserving original `Search volume` text.
- Implement [whatsup/news.py](C:/Users/bhke05279/Documents/WhatsUp/whatsup/news.py): query `https://news.google.com/rss/search` with `when:1d`, US locale parameters, and the trend phrase; select the first three distinct RSS results, decode publisher URLs, and extract readable article text with Trafilatura.
- If a publisher blocks extraction or an article is paywalled, retain that item using RSS title/source/description rather than dropping the trend. Apply timeouts and bounded concurrency; do not persist copyrighted article bodies.
- Implement [whatsup/summarizer.py](C:/Users/bhke05279/Documents/WhatsUp/whatsup/summarizer.py): load model/prompt config, fail fast when `OPENROUTER_API_KEY` is absent, make one OpenRouter request per trend, and retry only transient `429`/`5xx` failures with capped exponential backoff.
- Implement [whatsup/pipeline.py](C:/Users/bhke05279/Documents/WhatsUp/whatsup/pipeline.py) to orchestrate each trend independently so one failed article/model call does not remove a row. A failed summary receives an explicit actionable error/fallback message, preserving the 20-row contract.

## CLI and output
- Refactor [main.py](C:/Users/bhke05279/Documents/WhatsUp/main.py) into a thin entry point that loads config, validates credentials before network work, runs the pipeline, returns a DataFrame with exactly `Trends`, `Search volume`, `Started`, `LLM summary`, and writes `./outputs/trend_news_summary_<timestamp>.csv`.
- Update [README.md](C:/Users/bhke05279/Documents/WhatsUp/README.md) with setup, PowerShell `OPENROUTER_API_KEY` usage, execution command, output schema, expected cost/latency, Chrome requirement, and RSS/article-extraction limitations.

## Verification
- Add focused tests under [tests](C:/Users/bhke05279/Documents/WhatsUp/tests) for volume parsing/ranking, RSS deduplication and extraction fallback, OpenRouter retry/error handling, and the invariant that final output has 20 rows and only the four requested columns.
- Mock all external services in automated tests, then run one credentialed smoke test to confirm a real output CSV is produced without storing article bodies.