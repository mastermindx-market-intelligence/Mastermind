"""Capability checks for real browser tests."""

import importlib
import os


BROWSER_REASON_PREFIX = "BROWSER_UNAVAILABLE: "


def browser_launch_kwargs() -> dict:
    selection = {}
    executable_path = os.environ.get("MASTERMIND_BROWSER_EXECUTABLE")
    if executable_path:
        selection = {"executable_path": executable_path}
    channel = os.environ.get("MASTERMIND_BROWSER_CHANNEL")
    if channel:
        selection = {"channel": channel}
    return {
        "headless": True,
        "args": ["--no-sandbox"],
        **selection,
    }


def reset_browser_available_cache() -> None:
    browser_available.cache = None


def browser_available() -> tuple[bool, str]:
    if browser_available.cache is not None:
        return browser_available.cache
    try:
        importlib.import_module("playwright.sync_api")
    except ImportError:
        browser_available.cache = (
            False,
            BROWSER_REASON_PREFIX + "playwright not importable",
        )
        return browser_available.cache
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**browser_launch_kwargs())
            browser.close()
    except Exception as error:
        first_line = str(error).splitlines()[0]
        browser_available.cache = (False, BROWSER_REASON_PREFIX + first_line)
        return browser_available.cache
    browser_available.cache = (True, "")
    return browser_available.cache


browser_available.cache = None
