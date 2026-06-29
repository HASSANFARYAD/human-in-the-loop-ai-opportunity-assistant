from __future__ import annotations

import logging
import re
from typing import Any

from job_assistant.services.browser_automation import (
    click_element,
    close_context,
    element_exists,
    fill_form_field,
    get_or_create_context,
    navigate_and_wait,
    screenshot,
)

logger = logging.getLogger(__name__)

EASY_APPLY_URL_RE = re.compile(r"(linkedin\.com/jobs/search|linkedin\.com/jobs/view)", re.IGNORECASE)

EASY_APPLY_SELECTORS = {
    "easy_apply_button": "button.jobs-apply-button:not([disabled])",
    "easy_apply_modal": "div[data-test-modal-id='easy-apply-modal']",
    "next_button": "button[aria-label='Continue to next step']",
    "review_button": "button[aria-label='Review your application']",
    "submit_button": "button[aria-label='Submit application']",
    "close_button": "button[aria-label='Dismiss']",
    "discard_button": "button[aria-label='Discard']",
    "phone_input": "input[autocomplete='tel']",
    "phone_input_alt": "input[name='phone']",
    "resume_upload": "input[type='file'][accept*='pdf'], input[type='file'][accept*='doc']",
    "additional_questions": "div[data-test-form-builder]",
    "text_inputs": "input[type='text']",
    "textarea_inputs": "textarea",
    "dropdowns": "select",
}

FIELD_LABEL_MAP: dict[str, list[str]] = {
    "phone": ["phone", "phone number", "mobile", "contact number", "telephone"],
    "email": ["email", "email address", "e-mail"],
    "first_name": ["first name", "first", "given name"],
    "last_name": ["last name", "last", "family name", "surname"],
    "city": ["city", "town", "location"],
    "state": ["state", "province", "region"],
    "zip": ["zip", "zip code", "postal code", "post code"],
    "country": ["country"],
    "linkedin_url": ["linkedin", "linkedin url", "linkedin profile"],
    "portfolio_url": ["portfolio", "website", "personal website", "github"],
    "salary_expectation": ["salary", "salary expectation", "expected salary", "desired salary"],
    "work_authorization": ["work authorization", "authorized", "visa", "sponsorship", "work permit"],
    "gender": ["gender"],
    "race": ["race", "ethnicity"],
    "veteran": ["veteran", "military"],
    "disability": ["disability"],
    "education": ["education", "degree", "qualification"],
    "experience": ["years of experience", "experience"],
}

DEFAULT_LABEL_TO_SELECTOR: dict[str, str] = {
    "phone": 'input[autocomplete="tel"], input[name="phone"], input[id*="phone"]',
    "email": 'input[autocomplete="email"], input[name="email"], input[id*="email"]',
    "first_name": 'input[autocomplete="given-name"], input[name="firstName"]',
    "last_name": 'input[autocomplete="family-name"], input[name="lastName"]',
    "city": 'input[autocomplete="address-level2"], input[name="city"]',
    "state": 'input[autocomplete="address-level1"], input[name="state"]',
    "zip": 'input[autocomplete="postal-code"], input[name="postalCode"]',
    "country": 'input[name="country"]',
}


async def easy_apply_for_job(
    user_id: int,
    job_url: str,
    li_at: str = "",
    jsessionid: str = "",
    application_data: dict[str, str] | None = None,
    screenshot_dir: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    if not EASY_APPLY_URL_RE.search(job_url):
        return {"status": "skipped", "reason": "Not a LinkedIn job URL", "url": job_url}

    application_data = application_data or {}
    ctx = await get_or_create_context(user_id, li_at, jsessionid)

    try:
        page = await ctx.new_page()

        ok = await navigate_and_wait(page, job_url)
        if not ok:
            return {"status": "failed", "reason": "Failed to load job page", "url": job_url}

        if await element_exists(page, 'form[class*="sign-in"], input[name="session_key"]', 3000):
            return {"status": "failed", "reason": "LinkedIn login required — session cookies invalid or expired", "url": job_url}

        has_easy_apply = await element_exists(page, EASY_APPLY_SELECTORS["easy_apply_button"], 5000)
        if not has_easy_apply:
            external_link = await element_exists(page, 'a[href*="extern"], a[data-job-id*="apply"]', 3000)
            if external_link:
                return {"status": "skipped", "reason": "External apply link — not Easy Apply", "url": job_url}
            return {"status": "skipped", "reason": "No Easy Apply button found (already applied or closed)", "url": job_url}

        clicked = await click_element(page, EASY_APPLY_SELECTORS["easy_apply_button"])
        if not clicked:
            return {"status": "failed", "reason": "Could not click Easy Apply button", "url": job_url}

        await page.wait_for_timeout(2000)

        path = _capture_screenshot(page, screenshot_dir, user_id, job_url, "step1_modal") if screenshot_dir else ""

        steps = 0
        max_steps = 15
        submitted = False
        while steps < max_steps:
            steps += 1
            await page.wait_for_timeout(1000)

            if await element_exists(page, EASY_APPLY_SELECTORS["submit_button"], 2000):
                if dry_run:
                    await click_element(page, EASY_APPLY_SELECTORS["close_button"])
                    await click_element(page, EASY_APPLY_SELECTORS["discard_button"])
                    return {"status": "dry_run", "reason": "Dry run — would have submitted", "url": job_url, "screenshot": path if screenshot_dir else ""}
                clicked = await click_element(page, EASY_APPLY_SELECTORS["submit_button"])
                if clicked:
                    await page.wait_for_timeout(2000)
                    submitted = True
                break

            if await element_exists(page, EASY_APPLY_SELECTORS["review_button"], 2000):
                if dry_run:
                    await click_element(page, EASY_APPLY_SELECTORS["close_button"])
                    await click_element(page, EASY_APPLY_SELECTORS["discard_button"])
                    return {"status": "dry_run", "reason": "Dry run — would have submitted", "url": job_url, "screenshot": path if screenshot_dir else ""}
                clicked = await click_element(page, EASY_APPLY_SELECTORS["review_button"])
                if clicked:
                    await page.wait_for_timeout(1500)
                continue

            filled = await _fill_visible_fields(page, application_data)
            if not filled:
                break

            if await element_exists(page, EASY_APPLY_SELECTORS["next_button"], 2000):
                await click_element(page, EASY_APPLY_SELECTORS["next_button"])
            elif await element_exists(page, EASY_APPLY_SELECTORS["review_button"], 2000):
                continue
            else:
                break

        result = {
            "status": "submitted" if submitted else "failed",
            "reason": "Application submitted successfully" if submitted else f"Could not complete application after {steps} steps",
            "url": job_url,
            "steps_completed": steps,
            "screenshot": path if screenshot_dir else "",
        }

        if screenshot_dir:
            _capture_screenshot(page, screenshot_dir, user_id, job_url, f"result_{result['status']}")

        await page.close()
        return result

    except Exception as exc:
        logger.exception("Easy Apply failed for %s: %s", job_url, exc)
        return {"status": "error", "reason": str(exc), "url": job_url}


async def easy_apply_for_multiple(
    user_id: int,
    job_urls: list[str],
    li_at: str = "",
    jsessionid: str = "",
    application_data: dict[str, str] | None = None,
    screenshot_dir: str | None = None,
    dry_run: bool = True,
    max_applications: int = 10,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for i, url in enumerate(job_urls):
        if i >= max_applications:
            break
        result = await easy_apply_for_job(
            user_id, url, li_at, jsessionid, application_data, screenshot_dir, dry_run,
        )
        results.append(result)
        await asyncio.sleep(2)
    return results


async def _fill_visible_fields(page: Any, application_data: dict[str, str]) -> bool:
    filled_any = False

    for field_key, css_selectors in DEFAULT_LABEL_TO_SELECTOR.items():
        if field_key not in application_data:
            continue
        for selector in css_selectors.split(", "):
            if await fill_form_field(page, selector.strip(), application_data[field_key]):
                filled_any = True
                break

    for selector in EASY_APPLY_SELECTORS["text_inputs"], EASY_APPLY_SELECTORS["textarea_inputs"]:
        inputs = await page.query_selector_all(selector)
        for inp in inputs:
            try:
                label_el = await page.evaluate(
                    """(el) => {
                        const label = el.closest('div[data-test-form-builder]');
                        if (!label) return '';
                        const text = label.textContent || '';
                        const name = el.getAttribute('name') || '';
                        const placeholder = el.getAttribute('placeholder') || '';
                        return (text + '|' + name + '|' + placeholder).toLowerCase();
                    }""",
                    inp,
                )
                if not label_el:
                    continue
                matched = _match_label_to_field(label_el, application_data)
                if matched:
                    current_val = await inp.input_value()
                    if not current_val.strip():
                        await inp.fill(matched)
                        filled_any = True
            except Exception:
                continue

    for sel_name in ["phone_input", "phone_input_alt"]:
        sel = EASY_APPLY_SELECTORS.get(sel_name)
        if sel and "phone" in application_data:
            if await fill_form_field(page, sel, application_data["phone"]):
                filled_any = True

    dropdowns = await page.query_selector_all(EASY_APPLY_SELECTORS["dropdowns"])
    for dd in dropdowns:
        try:
            options = await dd.query_selector_all("option")
            for opt in options:
                opt_text = (await opt.inner_text()).strip().lower()
                if opt_text in ("yes", "true", "i've got it"):
                    opt_val = await opt.get_attribute("value")
                    if opt_val:
                        await dd.select_option(value=opt_val)
                        filled_any = True
                    break
                if opt_text == "no":
                    break
        except Exception:
            continue

    return filled_any


def _match_label_to_field(context_text: str, application_data: dict[str, str]) -> str | None:
    for field_key, labels in FIELD_LABEL_MAP.items():
        val = application_data.get(field_key)
        if not val:
            continue
        for label in labels:
            if label in context_text:
                return val
    return None


def _capture_screenshot(page: Any, screenshot_dir: str, user_id: int, job_url: str, stage: str) -> str:
    import hashlib
    import os as _os
    url_hash = hashlib.md5(job_url.encode()).hexdigest()[:8]
    if not _os.path.isdir(screenshot_dir):
        _os.makedirs(screenshot_dir, exist_ok=True)
    path = _os.path.join(screenshot_dir, f"easy_apply_{user_id}_{url_hash}_{stage}.png")
    return _os.path.abspath(path)
