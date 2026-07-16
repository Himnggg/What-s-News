from whatsup.config import NewsConfig
from whatsup.news import build_google_news_rss_url, get_top_news_articles


def _news_config() -> NewsConfig:
    return NewsConfig(
        top_n=3,
        locale_hl="en-US",
        locale_gl="US",
        locale_ceid="US:en",
        request_timeout_seconds=5,
        max_article_chars=500,
        max_workers=2,
    )


def test_build_google_news_rss_url_uses_us_locale_and_one_day_filter() -> None:
    url = build_google_news_rss_url("example trend", _news_config())

    assert "https://news.google.com/rss/search?" in url
    assert "example+trend+when%3A1d" in url
    assert "hl=en-US" in url
    assert "gl=US" in url
    assert "ceid=US%3Aen" in url


def test_get_top_news_articles_falls_back_to_rss_metadata(monkeypatch) -> None:
    rss = """
    <rss version="2.0">
      <channel>
        <item>
          <title>First story</title>
          <link>https://news.google.com/rss/articles/1</link>
          <source>Example News</source>
          <pubDate>Thu, 16 Jul 2026 01:00:00 GMT</pubDate>
          <description><![CDATA[<p>Fallback summary</p>]]></description>
        </item>
      </channel>
    </rss>
    """

    def fake_fetch_text(url: str, timeout_seconds: int) -> str | None:
        if "rss/search" in url:
            return rss
        return None

    monkeypatch.setattr("whatsup.news._fetch_text", fake_fetch_text)
    monkeypatch.setattr(
        "whatsup.news.resolve_news_url",
        lambda url, timeout_seconds: "https://example.com/story",
    )

    articles = get_top_news_articles("example trend", _news_config())

    assert len(articles) == 1
    assert articles[0].title == "First story"
    assert articles[0].source == "Example News"
    assert "Fallback summary" in articles[0].content
