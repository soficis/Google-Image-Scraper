# Google Image Scraper

Python tooling for collecting Google Images results at scale. The scraper runs headless by default, automatically keeps your ChromeDriver in sync, and can target single or multiple search terms from the command line.

If you are looking for image scrapers targeting Getty Images, Shutterstock, or Bing, check out [JJLimmm/Website-Image-Scraper](https://github.com/JJLimmm/Website-Image-Scraper).

## Requirements

- Windows (other platforms are untested)
- Google Chrome (latest version recommended)
- Python 3.10+ with `pip`

All Python dependencies are listed in `requirements.txt` (`selenium`, `pillow`, `requests`).

## Installation

```powershell
git clone https://github.com/ohyicong/Google-Image-Scraper
cd Google-Image-Scraper
python -m venv .venv
.venv\Scripts\Activate
pip install -r requirements.txt
```

The scraper will download or patch the matching ChromeDriver automatically the first time it runs.

## Quick start: single search

```powershell
python GoogleImageScraper.py --search "rivers cuomo" --limit 20
```

Downloads land in `photos/<search term>/` (falls back to `photos` inside the repo). Run `--help` to see the full list of options:

```text
usage: GoogleImageScraper.py [-h] --search SEARCH [SEARCH ...]
                             [--limit LIMIT] [--output OUTPUT]
                             [--webdriver-path WEBDRIVER_PATH]
                             [--min-resolution WIDTH HEIGHT]
                             [--max-resolution WIDTH HEIGHT]
                             [--max-missed MAX_MISSED]
                             [--keep-filenames] [--show-browser]
                             [--headless] [--verbose]
```

Key flags:

- `--search/-s`: one or more tokens that will be joined into the Google Images query (required).
- `--limit/-n`: maximum number of preview URLs to collect (default `50`).
- `--output/-o`: base directory for downloads (default `photos`).
- `--show-browser`: disable headless mode so you can watch the browser session.
- `--keep-filenames`: keep the remote filename instead of the generated `<search><index>` pattern.
- `--min-resolution`/`--max-resolution`: reject images outside of the given bounds (default `512x512` minimum).
- `--verbose`: promote the logger to DEBUG for troubleshooting Selenium interactions.

> **Tip:** Some hosts (e.g., Wikimedia) block automated downloads and may emit `403` errors. The scraper logs these events and continues with the remaining URLs.

## Batch runs

The `main.py` helper demonstrates how to schedule multiple queries with shared settings and optional threading. Edit the `default_terms` list or import `run_batch` in your own scripts:

```python
from main import build_default_settings, run_batch

settings = build_default_settings()
run_batch(["rivers cuomo", "brian wilson"], settings, max_workers=2)
```

Each worker uses the same configuration object, so tweak `build_default_settings()` (limit, headless mode, resolution bounds, etc.) to fit your workload.

## Troubleshooting

- Run with `--show-browser` if you need to inspect what Selenium is doing.
- Use `--verbose` to emit detailed thumbnail/preview diagnostics.
- If Chrome updates and the driver mismatch causes a startup failure, the scraper retries once with an auto-patched driver. Manual downloads are rarely necessary.
- Long-running sessions may trigger Google rate limits; lower `--limit` or increase `--max-missed` to trade off between persistence and runtime.

## FAQ

- **Why are some images missing?** Files that don't meet the resolution bounds or are served via blocked hosts are skipped. Check the log output for the exact reason.
- **Where are files saved?** `$OUTPUT/<search term>/` inside the working directory. Use `--keep-filenames` to retain original filenames.
- **Can I call the scraper from another script?** Yes—import `GoogleImageScraper` and instantiate it directly or call `run_cli([...])` with custom arguments.

## Demo video

[![Google Image Scraper walkthrough](https://github.com/ohyicong/Google-Image-Scraper/blob/master/youtube_thumbnail.PNG)](https://youtu.be/QZn_ZxpsIw4)

---

Run the scripts from a terminal (PowerShell, Command Prompt). Executing inside VS Code's debugger is not supported.
