# -*- coding: utf-8 -*-
"""
Created on Sat Jul 18 13:01:02 2020

@author: OHyic
"""
#import selenium drivers
import argparse
import logging
import time
from contextlib import suppress
from typing import List, Optional, Sequence, Set

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.remote.webelement import WebElement

#import helper libraries
from urllib.parse import quote_plus, urlparse
import os
import requests
import io
from PIL import Image
import re

#custom patch libraries
import patch


LOGGER_NAME = "google_image_scraper"
logger = logging.getLogger(LOGGER_NAME)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

class GoogleImageScraper:
    """High-level interface for collecting and downloading Google Image results."""

    INITIAL_LOAD_DELAY = 5
    SCROLL_ATTEMPTS = 12
    SCROLL_PAUSE_SECONDS = 1.5
    PREVIEW_WAIT_SECONDS = 2.5
    THUMBNAIL_SELECTOR = "img.YQ4gaf"
    PREVIEW_IMAGE_SELECTORS = ("img.n3VNCb", "img.sFlh5c")
    OVERLAY_SELECTORS = (".sfbg", "#searchform")
    VALID_PROTOCOLS = ("http://", "https://")

    def __init__(
        self,
        webdriver_path: str,
        image_path: str,
        search_key: str = "cat",
        number_of_images: int = 1,
        headless: bool = True,
        min_resolution: Sequence[int] = (0, 0),
        max_resolution: Sequence[int] = (1920, 1080),
        max_missed: int = 10,
    ) -> None:
        self._validate_number_of_images(number_of_images)
        self.search_key = search_key
        self.number_of_images = number_of_images
        self.headless = headless
        self.min_resolution = tuple(min_resolution)
        self.max_resolution = tuple(max_resolution)
        self.max_missed = max_missed
        self.webdriver_path = webdriver_path
        self.image_path = self._prepare_image_directory(image_path, search_key)
        self.driver = self._create_webdriver(webdriver_path, headless)
        self.url = f"https://www.google.com/search?tbm=isch&q={quote_plus(search_key)}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def find_image_urls(self) -> List[str]:
        """Return a list of image URLs for the configured search term."""

        logger.info("Gathering image links")
        collected_urls: Set[str] = set()
        missed_count = 0
        thumbnail_index = 0
        scroll_attempts = 0

        try:
            self.driver.get(self.url)
            time.sleep(self.INITIAL_LOAD_DELAY)
            while (
                len(collected_urls) < self.number_of_images
                and missed_count <= self.max_missed
            ):
                thumbnails = self._collect_thumbnails()
                logger.debug("Collected %d thumbnails (index %d)", len(thumbnails), thumbnail_index)

                if thumbnail_index >= len(thumbnails):
                    if scroll_attempts >= self.SCROLL_ATTEMPTS:
                        break
                    if not self._scroll_page():
                        break
                    scroll_attempts += 1
                    continue

                thumbnail = thumbnails[thumbnail_index]
                thumbnail_index += 1

                try:
                    self._open_thumbnail_preview(thumbnail)
                    preview_url = self._extract_preview_image_url(collected_urls)
                    if preview_url:
                        collected_urls.add(preview_url)
                        logger.info("%s \t #%d \t %s", self.search_key, len(collected_urls), preview_url)
                        missed_count = 0
                    else:
                        missed_count += 1
                except StaleElementReferenceException:
                    logger.debug("Thumbnail %s went stale before interaction; retrying later", thumbnail_index)
                    missed_count += 1
                    continue
                except WebDriverException as error:
                    logger.debug("Error processing thumbnail %s: %s", thumbnail_index, error)
                    missed_count += 1

        finally:
            self.driver.quit()
            self.driver = None
            logger.info("Google search ended")

        logger.debug("Found %d image URLs", len(collected_urls))
        return list(collected_urls)

    def save_images(self, image_urls: Sequence[str], keep_filenames: bool) -> None:
        """Download the provided image URLs to the configured destination."""

        if not image_urls:
            logger.info("No images to download.")
            return

        logger.info("Saving image, please wait...")
        for index, image_url in enumerate(image_urls):
            try:
                self._download_image(image_url, index, keep_filenames)
            except Exception as error:  # pylint: disable=broad-except
                logger.error("Download failed: %s", error)

        logger.info("Downloads completed. Some photos may be skipped if the format is unsupported or the resolution is out of range.")

    # ------------------------------------------------------------------
    # Driver helpers
    # ------------------------------------------------------------------
    def _create_webdriver(self, webdriver_path: str, headless: bool) -> webdriver.Chrome:
        if not os.path.isfile(webdriver_path):
            logger.info("Webdriver not found. Attempting to download the latest version.")
            if not patch.download_lastest_chromedriver():
                raise FileNotFoundError(
                    "Unable to locate chromedriver. Please download the correct version manually."
                )

        for attempt in range(2):
            try:
                options = self._build_chrome_options(headless)
                service = ChromeService(executable_path=webdriver_path)
                driver = webdriver.Chrome(service=service, options=options)
                driver.set_window_size(1400, 1050)
                driver.get("https://www.google.com")
                self._accept_consent_if_present(driver)
                return driver
            except Exception as error:  # pylint: disable=broad-except
                if attempt == 0 and self._attempt_driver_patch(error):
                    continue
                raise RuntimeError("Failed to create Chrome driver") from error

        raise RuntimeError("Failed to initialize Chrome driver after patching attempt")

    @staticmethod
    def _build_chrome_options(headless: bool) -> Options:
        options = Options()
        if headless:
            # Use the modern headless mode for recent Chrome versions.
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--log-level=3")
        return options

    @staticmethod
    def _accept_consent_if_present(driver: webdriver.Chrome) -> None:
        with suppress(Exception):
            WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "W0wltc"))).click()

    def _attempt_driver_patch(self, error: Exception) -> bool:
        pattern = r"(\d+\.\d+\.\d+\.\d+)"
        match = re.search(pattern, str(error))
        if not match:
            return False
        logger.info("Attempting to patch chromedriver to version %s", match.group())
        return patch.download_lastest_chromedriver(match.group())

    # ------------------------------------------------------------------
    # Page interaction helpers
    # ------------------------------------------------------------------
    def _collect_thumbnails(self) -> List[WebElement]:
        return self.driver.find_elements(By.CSS_SELECTOR, self.THUMBNAIL_SELECTOR)

    def _scroll_page(self) -> bool:
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(self.SCROLL_PAUSE_SECONDS)
        new_height = self.driver.execute_script("return document.body.scrollHeight")
        return new_height > last_height

    def _open_thumbnail_preview(self, thumbnail: WebElement) -> None:
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", thumbnail)
        time.sleep(0.5)
        self._dismiss_overlays()

        target = self._find_click_target(thumbnail)
        with suppress(WebDriverException):
            logger.debug("Clicking thumbnail via WebElement.click()")
            target.click()
            time.sleep(self.PREVIEW_WAIT_SECONDS)
            return

        # Fallback to JavaScript click in case of overlay issues.
        logger.debug("Falling back to JavaScript click")
        self.driver.execute_script("arguments[0].click();", target)
        time.sleep(self.PREVIEW_WAIT_SECONDS)

    @staticmethod
    def _find_click_target(thumbnail: WebElement) -> WebElement:
        with suppress(NoSuchElementException):
            return thumbnail.find_element(By.XPATH, "../../..")
        with suppress(NoSuchElementException):
            return thumbnail.find_element(By.XPATH, "../..")
        return thumbnail

    def _dismiss_overlays(self) -> None:
        for selector in self.OVERLAY_SELECTORS:
            script = (
                "const el = document.querySelector(arguments[0]);"
                "if (el) { el.style.display = 'none'; el.style.pointerEvents = 'none'; }"
            )
            self.driver.execute_script(script, selector)

    def _extract_preview_image_url(self, existing_urls: Set[str]) -> Optional[str]:
        preview_images: List[WebElement] = []
        for selector in self.PREVIEW_IMAGE_SELECTORS:
            matches = self.driver.find_elements(By.CSS_SELECTOR, selector)
            if matches:
                logger.debug("Selector %s yielded %d candidates", selector, len(matches))
            preview_images.extend(matches)
        logger.debug("Found %d preview candidates", len(preview_images))
        if not preview_images:
            with suppress(Exception):
                sample = self.driver.execute_script(
                    "return Array.from(document.querySelectorAll('div[data-query] img')).slice(0, 5).map(img => ({'class': img.className, 'src': img.src}));"
                )
                logger.debug("Preview probe sample: %s", sample)
        for preview in preview_images:
            candidate = preview.get_attribute("src")
            logger.debug("Preview candidate src: %s", candidate)
            if self._is_valid_image_url(candidate, existing_urls):
                return candidate
        return None

    # ------------------------------------------------------------------
    # Validation and utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_number_of_images(number_of_images: int) -> None:
        if not isinstance(number_of_images, int) or number_of_images < 1:
            raise ValueError("number_of_images must be a positive integer")

    @staticmethod
    def _prepare_image_directory(root_path: str, search_key: str) -> str:
        directory = os.path.join(root_path, search_key)
        os.makedirs(directory, exist_ok=True)
        return directory

    def _is_valid_image_url(self, url: Optional[str], existing_urls: Set[str]) -> bool:
        if not url:
            return False
        if url in existing_urls:
            return False
        if not url.startswith(self.VALID_PROTOCOLS):
            return False
        if url.lower().endswith(".svg"):
            return False
        return True

    # ------------------------------------------------------------------
    # Download helpers
    # ------------------------------------------------------------------
    def _download_image(self, image_url: str, index: int, keep_filenames: bool) -> None:
        logger.info("Image url: %s", image_url)
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()

        search_prefix = "".join(char for char in self.search_key if char.isalnum())
        with Image.open(io.BytesIO(response.content)) as image_from_web:
            filename = self._compute_filename(image_url, index, search_prefix, image_from_web.format, keep_filenames)
            destination = os.path.join(self.image_path, filename)
            self._save_image_asset(image_from_web, destination)

            if not self._is_within_resolution(image_from_web.size):
                logger.debug("Removing %s due to resolution %s", destination, image_from_web.size)
                os.remove(destination)
                return

            logger.info("%s \t %s \t Image saved at: %s", self.search_key, index, destination)

    @staticmethod
    def _compute_filename(
        image_url: str,
        index: int,
        search_prefix: str,
        image_format: Optional[str],
        keep_filenames: bool,
    ) -> str:
        extension = (image_format or "jpg").lower()
        if keep_filenames:
            parsed = urlparse(image_url)
            sanitized_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            base_name = os.path.splitext(os.path.basename(sanitized_url))[0]
            base_name = base_name or f"image_{index}"
            return f"{base_name}.{extension}"
        return f"{search_prefix}{index}.{extension}"

    def _save_image_asset(self, image_from_web: Image.Image, destination: str) -> None:
        try:
            image_from_web.save(destination)
        except OSError:
            rgb_image = image_from_web.convert("RGB")
            rgb_image.save(destination)

    def _is_within_resolution(self, resolution: Sequence[int]) -> bool:
        if not resolution:
            return True
        width, height = resolution
        min_width, min_height = self.min_resolution
        max_width, max_height = self.max_resolution
        if width < min_width or height < min_height:
            return False
        if width > max_width or height > max_height:
            return False
        return True


def parse_cli_arguments(args: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments for the standalone scraper entry point."""

    parser = argparse.ArgumentParser(description="Download images from Google Images.")
    parser.add_argument(
        "--search",
        "-s",
        nargs="+",
        required=True,
        help="Search keywords used on Google Images (e.g. --search rivers cuomo)",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=50,
        help="Maximum number of images to fetch (default: 50)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="photos",
        help="Base directory for downloaded images (default: photos)",
    )
    parser.add_argument(
        "--webdriver-path",
        default=None,
        help="Path to chromedriver executable (defaults to ./webdriver/<platform-specific>)",
    )
    parser.add_argument(
        "--min-resolution",
        nargs=2,
        type=int,
        metavar=("WIDTH", "HEIGHT"),
        default=(512, 512),
        help="Minimum accepted resolution in pixels (default: 512 512)",
    )
    parser.add_argument(
        "--max-resolution",
        nargs=2,
        type=int,
        metavar=("WIDTH", "HEIGHT"),
        default=(9999, 9999),
        help="Maximum accepted resolution in pixels (default: 9999 9999)",
    )
    parser.add_argument(
        "--max-missed",
        type=int,
        default=10,
        help="Maximum number of consecutive misses before stopping (default: 10)",
    )
    parser.add_argument(
        "--keep-filenames",
        action="store_true",
        help="Preserve original filenames from the remote URLs.",
    )
    parser.add_argument(
        "--show-browser",
        dest="headless",
        action="store_false",
        help="Show the Chrome browser window while scraping.",
    )
    parser.add_argument(
        "--headless",
        dest="headless",
        action="store_true",
        help="Force headless mode (default).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging.",
    )
    parser.set_defaults(headless=True)
    return parser.parse_args(args)


def run_cli(cli_args: Optional[Sequence[str]] = None) -> None:
    """Run the scraper as a standalone command-line utility."""

    args = parse_cli_arguments(cli_args)

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    search_term = " ".join(args.search)
    webdriver_path = args.webdriver_path or os.path.normpath(
        os.path.join(os.getcwd(), "webdriver", patch.webdriver_executable())
    )

    scraper = GoogleImageScraper(
        webdriver_path=webdriver_path,
        image_path=args.output,
        search_key=search_term,
        number_of_images=args.limit,
        headless=args.headless,
        min_resolution=tuple(args.min_resolution),
        max_resolution=tuple(args.max_resolution),
        max_missed=args.max_missed,
    )

    image_urls = scraper.find_image_urls()
    scraper.save_images(image_urls, keep_filenames=args.keep_filenames)


if __name__ == "__main__":
    run_cli()
