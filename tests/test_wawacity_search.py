import os
import re

import pytest
from wawacity.scrapers.audiobook import AudiobookScraper, audiobook_scraper
from wawacity.scrapers.movie import MovieScraper, movie_scraper
from wawacity.scrapers.series import SeriesScraper, series_scraper

BASE_URL = "https://www.wawacity.cafe"
PROJECT_ROOT = os.path.dirname(__file__)

# If tests are launched all together for the first time they might fail due to too many parallel http request to wawacity.
# Launch them one by one.


@pytest.mark.asyncio
@pytest.mark.vcr(record_mode="new_episodes")
@pytest.mark.parametrize(
    "scraper, search_query, year, expected_slug, media_type",
    [
        # --- FILMS ---
        # without year
        pytest.param(
            movie_scraper,
            "La Belle Verte",
            None,
            "la-belle-verte",
            "film",
            marks=pytest.mark.xfail(
                reason="date not provided, so an unrelated media is returned",
                strict=True,
                raises=AssertionError,
            ),
        ),
        # with year
        (movie_scraper, "La Belle Verte", "1996", "la-belle-verte", "film"),
        # --- SERIES ---
        # without year
        pytest.param(
            series_scraper,
            "The Boys",
            None,
            "the-boys",
            "serie",
            marks=pytest.mark.xfail(
                reason="date not provided, so an unrelated media is returned",
                strict=True,
                raises=AssertionError,
            ),
        ),
        # with year
        (series_scraper, "The Boys", "2019", "the-boys", "serie"),
    ],
)
async def test_wawacity_search_flow(
    scraper: MovieScraper | SeriesScraper | AudiobookScraper,
    search_query: str,
    year: str | None,
    expected_slug: str,
    media_type: str,
):
    if scraper == movie_scraper:
        result = await scraper._search_movie(
            title=search_query, year=year, base_url=BASE_URL
        )
    else:
        result = await scraper._search_series(
            title=search_query, year=year, base_url=BASE_URL
        )

    assert result is not None

    link = result["link"]

    # Check media type
    assert f"?p={media_type}" in link

    # Check slug and numerical id
    pattern = rf"id=\d+-{re.escape(expected_slug)}(?:-.*)?"

    assert (
        re.search(pattern, link) is not None
    ), f"L'URL '{link}' does not match expected slug pattern '{expected_slug}'"

    # Check query
    assert search_query.lower() in result["text"].lower()


@pytest.mark.asyncio
@pytest.mark.vcr(record_mode="new_episodes")
async def test_search_audiobook():
    search_query = "La terre"
    expected_detail_path = "?p=ebook&id=84348-la-terre-mile-zola-2026"

    result = await audiobook_scraper._search_audiobook(search_query, BASE_URL)

    assert result is not None
    assert result["link"] == expected_detail_path
    assert search_query.lower() in result["text"].lower()


@pytest.mark.asyncio
@pytest.mark.vcr(record_mode="new_episodes")
async def test_search_no_results():
    result = await movie_scraper._search_movie("ImagiedMovie", None, BASE_URL)
    assert result is None
