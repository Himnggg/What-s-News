import pandas as pd
import pytest

from whatsup.trends import parse_search_volume, select_top_trends


def test_parse_search_volume_handles_suffixes() -> None:
    assert parse_search_volume("20K+") == 20_000
    assert parse_search_volume("1.5M+") == 1_500_000
    assert parse_search_volume("2,500+") == 2_500


def test_parse_search_volume_rejects_unknown_format() -> None:
    with pytest.raises(ValueError, match="Unsupported search volume"):
        parse_search_volume("many")


def test_select_top_trends_sorts_by_numeric_volume() -> None:
    trends = pd.DataFrame(
        {
            "Trends": ["low", "high", "medium"],
            "Search volume": ["20K+", "1M+", "200K+"],
            "Started": [
                "July 16, 2026 at 1:00:00 AM UTC+8",
                "July 16, 2026 at 2:00:00 AM UTC+8",
                "July 16, 2026 at 3:00:00 AM UTC+8",
            ],
        }
    )

    result = select_top_trends(trends, limit=2)

    assert result["Trends"].tolist() == ["high", "medium"]
    assert result.columns.tolist() == ["Trends", "Search volume", "Started"]
