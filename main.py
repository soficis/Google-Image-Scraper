"""Convenience entry point for scraping multiple Google Image search terms."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Iterable, List

from GoogleImageScraper import GoogleImageScraper
from patch import webdriver_executable


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScraperSettings:
    webdriver_path: str
    image_root: str
    number_of_images: int
    headless: bool
    min_resolution: tuple[int, int]
    max_resolution: tuple[int, int]
    max_missed: int
    keep_filenames: bool


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def run_search(search_key: str, settings: ScraperSettings) -> None:
    """Execute a single Google Images search and download the results."""

    logger.info("Starting scrape for '%s'", search_key)
    try:
        scraper = GoogleImageScraper(
            webdriver_path=settings.webdriver_path,
            image_path=settings.image_root,
            search_key=search_key,
            number_of_images=settings.number_of_images,
            headless=settings.headless,
            min_resolution=settings.min_resolution,
            max_resolution=settings.max_resolution,
            max_missed=settings.max_missed,
        )
        image_urls = scraper.find_image_urls()
        scraper.save_images(image_urls, keep_filenames=settings.keep_filenames)
        logger.info("Completed scrape for '%s' (%d images)", search_key, len(image_urls))
    except Exception as error:  # pylint: disable=broad-except
        logger.exception("Scrape failed for '%s': %s", search_key, error)


def unique_search_terms(search_terms: Iterable[str]) -> List[str]:
    """Return a sorted list of de-duplicated search terms."""

    cleaned_terms = {term.strip() for term in search_terms if term.strip()}
    return sorted(cleaned_terms)


def build_default_settings() -> ScraperSettings:
    cwd = os.getcwd()
    webdriver_path = os.path.normpath(os.path.join(cwd, "webdriver", webdriver_executable()))
    image_root = os.path.normpath(os.path.join(cwd, "photos"))
    return ScraperSettings(
        webdriver_path=webdriver_path,
        image_root=image_root,
        number_of_images=200,
        headless=True,
        min_resolution=(512, 512),
        max_resolution=(9999, 9999),
        max_missed=10,
        keep_filenames=False,
    )


def run_batch(search_terms: Iterable[str], settings: ScraperSettings, max_workers: int = 1) -> None:
    """Run the scraper across multiple search terms in parallel."""

    terms = unique_search_terms(search_terms)
    if not terms:
        logger.warning("No search terms supplied; nothing to do.")
        return

    logger.info("Scheduling %d search term(s) with %d worker(s)", len(terms), max_workers)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for term in terms:
            executor.submit(run_search, term, settings)


def main() -> None:
    configure_logging()
    settings = build_default_settings()
    default_terms = ["Weird Al Yankovic"]
    run_batch(default_terms, settings, max_workers=1)


if __name__ == "__main__":
    main()