from __future__ import annotations

import re

import pytest
from _asset_inventory import active_import_ui_paths
from _browser_probe import BrowserProbe
from playwright.async_api import Page, expect

pytestmark = pytest.mark.only_browser("chromium")


@pytest.mark.asyncio(loop_scope="session")
async def test_import_ui_run_wizard_happy_path(page: Page, e2e_web_base_url: str) -> None:
    probe = BrowserProbe(page)
    expected = active_import_ui_paths()

    response = await page.goto(f"{e2e_web_base_url}/import/ui/", wait_until="domcontentloaded")
    assert response is not None and response.ok, "GET /import/ui/ did not return success"

    await expect(page).to_have_title(re.compile(r"AudioMason Import"))
    await expect(page.locator("#tabs")).to_be_visible()
    await expect(page.locator("#start")).to_be_visible()
    await probe.wait_for_script_paths(expected)
    assert await probe.filtered_script_paths("/import/ui/assets/") == expected

    await page.select_option("#mode", "stage")
    await page.locator("#start").click()

    await expect(page.locator("#status")).to_contain_text("session_id:")
    await expect(page.locator("#step")).to_contain_text("Step:")

    author_selection = page.locator('#step [data-v3-payload-key="selection"]')
    await expect(author_selection).to_be_visible()
    await author_selection.fill("1")
    await page.locator("#submit").click()

    state_view = page.locator("#state")
    await expect(state_view).to_contain_text('"current_step_id": "select_books"')

    book_selection = page.locator('#step [data-v3-payload-key="selection"]')
    await expect(book_selection).to_be_visible()
    await book_selection.fill("1")
    await page.locator("#submit").click()

    await expect(state_view).to_contain_text('"selected_book_ids": [')
    await expect(state_view).to_contain_text('"current_step_id": "effective_author_title"')
    await probe.assert_clean()
