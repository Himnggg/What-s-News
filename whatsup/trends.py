from __future__ import annotations

import re

import pandas as pd
from trendspyg import download_google_trends_csv

from whatsup.config import TrendsConfig

TREND_COLUMN = "Trends"
SEARCH_VOLUME_COLUMN = "Search volume"
STARTED_COLUMN = "Started"

TREND_OUTPUT_COLUMNS = [TREND_COLUMN, SEARCH_VOLUME_COLUMN, STARTED_COLUMN]
VOLUME_PATTERN = re.compile(r"(?P<number>\d+(?:\.\d+)?)\s*(?P<suffix>[KMB])?", re.IGNORECASE)
TIMEZONE_PATTERN = re.compile(r" UTC(?P<sign>[+-])(?P<hour>\d{1,2})(?::?(?P<minute>\d{2}))?$")
VOLUME_MULTIPLIERS = {
    "": 1,
    "K": 1_000,
    "M": 1_000_000,
    "B": 1_000_000_000,
}


def fetch_trends(config: TrendsConfig) -> pd.DataFrame:
    """Fetch Google Trends records as a pandas DataFrame.

    Args:
        config: Trends retrieval configuration.

    Returns:
        Raw trends DataFrame from trendspyg.

    Raises:
        TypeError: If trendspyg does not return a DataFrame.
    """
    trends = download_google_trends_csv(
        geo=config.country_code,
        hours=config.window_hours,
        category="all",
        download_dir=str(config.download_dir),
        output_format="dataframe",
    )
    if not isinstance(trends, pd.DataFrame):
        raise TypeError("Google Trends did not return a pandas DataFrame.")
    return trends


def parse_search_volume(search_volume: object) -> int:
    """Parse Google Trends search-volume text into a comparable integer.

    Args:
        search_volume: Value such as "20K+", "1M+", or "1,500".

    Returns:
        Numeric lower-bound volume.

    Raises:
        ValueError: If the value cannot be parsed.
    """
    value = str(search_volume).replace(",", "").replace("+", "").strip()
    match = VOLUME_PATTERN.fullmatch(value)
    if not match:
        raise ValueError(f"Unsupported search volume: {search_volume!r}")

    number = float(match.group("number"))
    suffix = (match.group("suffix") or "").upper()
    return int(number * VOLUME_MULTIPLIERS[suffix])


def select_top_trends(trends: pd.DataFrame, limit: int) -> pd.DataFrame:
    """Sort trends by search volume and return the top records.

    Args:
        trends: Raw Google Trends DataFrame.
        limit: Number of records to return.

    Returns:
        DataFrame containing `Trends`, `Search volume`, and `Started`.

    Raises:
        ValueError: If required columns are missing or there are too few rows.
    """
    _validate_trend_columns(trends)
    if len(trends) < limit:
        raise ValueError(f"Expected at least {limit} trends, found {len(trends)}.")

    ranked_trends = trends.copy()
    ranked_trends["_search_volume_numeric"] = ranked_trends[SEARCH_VOLUME_COLUMN].map(
        parse_search_volume
    )
    ranked_trends["_started_sort"] = ranked_trends[STARTED_COLUMN].map(parse_started_at)

    ranked_trends = ranked_trends.sort_values(
        by=["_search_volume_numeric", "_started_sort", TREND_COLUMN],
        ascending=[False, False, True],
        kind="mergesort",
    )

    return ranked_trends.head(limit).loc[:, TREND_OUTPUT_COLUMNS].reset_index(drop=True)


def _validate_trend_columns(trends: pd.DataFrame) -> None:
    missing_columns = set(TREND_OUTPUT_COLUMNS) - set(trends.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Trends DataFrame is missing required columns: {missing}")


def parse_started_at(started_at: object) -> pd.Timestamp:
    """Parse Google Trends `Started` text into a UTC timestamp."""
    value = str(started_at).replace("\u202f", " ").replace("\xa0", " ").strip()
    normalized_value = TIMEZONE_PATTERN.sub(_normalize_timezone, value)
    return pd.to_datetime(
        normalized_value,
        format="%B %d, %Y at %I:%M:%S %p %z",
        errors="coerce",
        utc=True,
    )


def _normalize_timezone(match: re.Match[str]) -> str:
    sign = match.group("sign")
    hour = match.group("hour").zfill(2)
    minute = match.group("minute") or "00"
    return f" {sign}{hour}{minute}"
