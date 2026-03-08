from __future__ import annotations

import re

import pytest
from _asset_inventory import active_patchhub_main_paths
from _browser_probe import BrowserProbe
from playwright.async_api import Page, expect

pytestmark = pytest.mark.only_browser("chromium")


@pytest.mark.asyncio(loop_scope="session")
async def test_patchhub_main_ui_boots_with_expected_assets(
    page: Page,
    e2e_patchhub_base_url: str,
) -> None:
    probe = BrowserProbe(page)
    expected = active_patchhub_main_paths()

    response = await page.goto(f"{e2e_patchhub_base_url}/", wait_until="domcontentloaded")
    assert response is not None and response.ok, "GET / did not return a successful response"

    await expect(page).to_have_title(re.compile(r"PatchHub"))
    await probe.wait_for_script_paths(expected)
    assert await probe.filtered_script_paths("/static/") == expected

    left_titles = page.locator(".panel-left section.card h2")
    assert await left_titles.all_text_contents() == [
        "Active job",
        "Workspaces",
        "Stats",
        "Runs",
    ]

    right_titles = page.locator(".panel-right section.card h2")
    assert await right_titles.all_text_contents() == [
        "Progress",
        "Jobs",
        "Preview",
        "Advanced",
    ]

    await expect(page.locator("#refreshAll")).to_be_visible()
    await expect(page.locator("#parseBtn")).to_be_visible()
    await expect(page.locator("#previewToggle")).to_be_visible()

    benign_page_errors = [
        item for item in probe.page_errors if "signal is aborted without reason" in item
    ]
    assert benign_page_errors == probe.page_errors
    issues = probe.console_errors + probe.failed_responses
    assert not issues, "Frontend issues: " + " | ".join(issues)
