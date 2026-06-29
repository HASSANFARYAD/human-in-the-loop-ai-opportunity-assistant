from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_BROWSER = None
_contexts: dict[int, Any] = {}
_lock = asyncio.Lock()


async def _get_browser():
    global _BROWSER
    if _BROWSER is None or not _BROWSER.is_connected():
        from playwright.async_api import async_playwright
        p = await async_playwright().start()
        _BROWSER = await p.chromium.launch(
            headless=os.getenv("BROWSER_HEADLESS", "true").strip().lower() in {"1", "true", "yes"},
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
    return _BROWSER


async def close_browser():
    global _BROWSER
    async with _lock:
        for uid in list(_contexts.keys()):
            await _close_context(uid)
        if _BROWSER:
            try:
                await _BROWSER.close()
            except Exception:
                pass
            _BROWSER = None


async def _close_context(user_id: int):
    ctx = _contexts.pop(user_id, None)
    if ctx:
        try:
            await ctx.close()
        except Exception:
            pass


def _linkedin_cookies(li_at: str = "", jsessionid: str = "") -> list[dict[str, Any]]:
    cookies = [
        {"name": "li_at", "value": li_at, "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True},
        {"name": "JSESSIONID", "value": f'"{jsessionid}"' if jsessionid and not jsessionid.startswith('"') else jsessionid, "domain": ".linkedin.com", "path": "/", "httpOnly": False, "secure": True},
        {"name": "lang", "value": "en_US", "domain": ".linkedin.com", "path": "/", "httpOnly": False, "secure": False},
    ]
    return [c for c in cookies if c["value"]]


async def get_or_create_context(user_id: int, linkedin_li_at: str = "", linkedin_jsessionid: str = "") -> Any:
    async with _lock:
        if user_id in _contexts:
            ctx = _contexts[user_id]
            try:
                page = await ctx.new_page()
                await page.close()
                return ctx
            except Exception:
                await _close_context(user_id)
        browser = await _get_browser()
        ctx = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        if linkedin_li_at:
            cookies = _linkedin_cookies(linkedin_li_at, linkedin_jsessionid)
            if cookies:
                await ctx.add_cookies(cookies)
        _contexts[user_id] = ctx
        return ctx


async def close_context(user_id: int):
    async with _lock:
        await _close_context(user_id)


async def navigate_and_wait(page: Any, url: str, timeout: int = 30000) -> bool:
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        await page.wait_for_load_state("networkidle", timeout=10000)
        return resp is not None and resp.ok
    except Exception as exc:
        logger.warning("navigate_and_wait(%s) failed: %s", url, exc)
        return False


async def screenshot(page: Any, path: str) -> str:
    await page.screenshot(path=path, full_page=True)
    return path


async def fill_form_field(page: Any, selector: str, value: str) -> bool:
    try:
        await page.wait_for_selector(selector, timeout=5000)
        await page.fill(selector, value)
        return True
    except Exception as exc:
        logger.debug("fill_form_field(%s) failed: %s", selector, exc)
        return False


async def click_element(page: Any, selector: str, timeout: int = 5000) -> bool:
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        await page.click(selector)
        return True
    except Exception as exc:
        logger.debug("click_element(%s) failed: %s", selector, exc)
        return False


async def element_exists(page: Any, selector: str, timeout: int = 3000) -> bool:
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        return True
    except Exception:
        return False
