from __future__ import annotations

import json
import re
from urllib import request

import pytest
from _asset_inventory import active_import_ui_paths
from _browser_probe import BrowserProbe
from playwright.async_api import Page, expect

pytestmark = pytest.mark.only_browser("chromium")


TEST_WIZARD = {
    "version": 3,
    "entry_step_id": "ask_author",
    "nodes": [
        {
            "step_id": "ask_author",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "Author",
                    "prompt": "Enter author",
                    "prefill": "Author A",
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.ask_author.value",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
        {
            "step_id": "ask_title",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "Title",
                    "prompt": "Enter title",
                    "prefill": "Book One",
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.ask_title.value",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
        {
            "step_id": "stop",
            "op": {
                "primitive_id": "ctrl.stop",
                "primitive_version": 1,
                "inputs": {},
                "writes": [],
            },
        },
    ],
    "edges": [
        {"from": "ask_author", "to": "ask_title"},
        {"from": "ask_title", "to": "stop"},
    ],
}


def _post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=10) as response:
        assert response.status == 200
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str) -> dict[str, object]:
    with request.urlopen(url, timeout=10) as response:
        assert response.status == 200
        return json.loads(response.read().decode("utf-8"))


def _install_test_wizard(base_url: str) -> None:
    posted = _post_json(
        f"{base_url}/import/ui/wizard-definition",
        {"definition": TEST_WIZARD},
    )
    assert posted["definition"]["entry_step_id"] == "ask_author"
    activated = _post_json(
        f"{base_url}/import/ui/wizard-definition/activate",
        {},
    )
    assert activated["definition"]["entry_step_id"] == "ask_author"


async def _read_state(page: Page) -> dict[str, object]:
    raw = await page.locator("#state").text_content()
    assert raw
    payload = json.loads(raw)
    assert isinstance(payload, dict)
    return payload


def _advance_default_v3_session_to_final_summary(
    base_url: str, session_id: str
) -> dict[str, object]:
    while True:
        state = _get_json(f"{base_url}/import/ui/session/{session_id}/state")
        current_step_id = state.get("current_step_id")
        if current_step_id == "final_summary_confirm":
            return state
        assert isinstance(current_step_id, str) and current_step_id

        step = _get_json(f"{base_url}/import/ui/session/{session_id}/step/{current_step_id}")
        primitive_id = str(step.get("primitive_id") or "")
        ui = step.get("ui")
        ui_obj = ui if isinstance(ui, dict) else {}
        prefill = ui_obj.get("prefill")
        default_value = ui_obj.get("default_value")

        if primitive_id == "ui.prompt_confirm":
            payload: dict[str, object] = {"confirmed": True}
        elif primitive_id == "ui.prompt_select":
            selection = prefill if isinstance(prefill, str) else default_value
            payload = {"selection": selection if isinstance(selection, str) else "all"}
        else:
            value = prefill if isinstance(prefill, str) else default_value
            payload = {"value": value if isinstance(value, str) else ""}

        _post_json(
            f"{base_url}/import/ui/session/{session_id}/step/{current_step_id}",
            payload,
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_import_ui_run_wizard_happy_path(page: Page, e2e_web_base_url: str) -> None:
    _install_test_wizard(e2e_web_base_url)

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

    author_value = page.locator('#step [data-v3-payload-key="value"]')
    await expect(author_value).to_be_visible()
    await expect(author_value).to_have_value("Author A")
    await page.locator("#submit").click()

    title_value = page.locator('#step [data-v3-payload-key="value"]')
    await expect(title_value).to_be_visible()
    await expect(title_value).to_have_value("Book One")
    await page.locator("#submit").click()

    await expect(page.locator("#step")).to_contain_text("Step: stop")
    await expect(page.locator("#step")).to_contain_text("Session status: completed")
    await probe.assert_clean()


@pytest.mark.asyncio(loop_scope="session")
async def test_import_ui_default_v3_auto_enters_processing(
    page: Page, e2e_web_v3_base_url: str
) -> None:
    probe = BrowserProbe(page)
    expected = active_import_ui_paths()

    response = await page.goto(
        f"{e2e_web_v3_base_url}/import/ui/",
        wait_until="domcontentloaded",
    )
    assert response is not None and response.ok, "GET /import/ui/ did not return success"

    await probe.wait_for_script_paths(expected)
    assert await probe.filtered_script_paths("/import/ui/assets/") == expected

    await expect(page.locator("#startProcessing")).to_have_count(0)

    await page.select_option("#mode", "stage")
    await page.locator("#start").click()
    await expect(page.locator("#status")).to_contain_text("session_id:")
    state = await _read_state(page)
    session_id = state.get("session_id")
    assert isinstance(session_id, str) and session_id

    _advance_default_v3_session_to_final_summary(e2e_web_v3_base_url, session_id)
    await page.locator("#reload").click()
    await expect(page.locator("#step")).to_contain_text("Step: final_summary_confirm")

    confirm = page.locator('#step [data-v3-payload-key="confirmed"]')
    await expect(confirm).to_be_visible()
    await confirm.check()
    await expect(page.locator("#startProcessing")).to_have_count(0)

    await page.locator("#submit").click()
    await expect(page.locator("#step")).to_contain_text("Step: processing")
    await expect(page.locator("#step")).to_contain_text("Session status: processing")
    await expect(page.locator("#startProcessing")).to_have_count(0)
    await probe.assert_clean()
