from __future__ import annotations

import pytest
from _browser_probe import BrowserProbe
from playwright.async_api import Page

pytestmark = pytest.mark.only_browser("chromium")


@pytest.mark.asyncio(loop_scope="session")
async def test_import_ui_flow_editor_shell_is_present_and_wired(
    page: Page,
    e2e_web_base_url: str,
) -> None:
    probe = BrowserProbe(page)

    response = await page.goto(
        f"{e2e_web_base_url}/import/ui/",
        wait_until="domcontentloaded",
        timeout=10_000,
    )
    assert response is not None and response.ok, "GET /import/ui/ did not return success"

    shell = await page.evaluate(
        """
        () => ({
          hasFlowTabButton: !!document.querySelector(
            '#tabs .tabBtn[data-tab="flow"]'
          ),
          hasReloadAll: !!document.getElementById('flowReloadAll'),
          hasValidateAll: !!document.getElementById('flowValidateAll'),
          hasFlowStepHeader: !!document.getElementById('flowStepHeader'),
          hasTransitionsPanel: !!document.getElementById('flowTransitionsPanel'),
          hasPalettePanel: !!document.getElementById('flowPalettePanel'),
        })
        """
    )
    assert shell == {
        "hasFlowTabButton": True,
        "hasReloadAll": True,
        "hasValidateAll": True,
        "hasFlowStepHeader": True,
        "hasTransitionsPanel": True,
        "hasPalettePanel": True,
    }

    wiring = await page.evaluate(
        """
        () => ({
          hasFlowEditorState: !!window.AM2FlowEditorState,
          hasDslEditorV3: !!window.AM2DSLEditorV3,
          hasWizardDefinitionEditor: !!window.AM2WizardDefinitionEditor,
          hasReloadAll: !!(window.AM2UI && window.AM2UI.doReloadAll),
        })
        """
    )
    assert wiring == {
        "hasFlowEditorState": True,
        "hasDslEditorV3": True,
        "hasWizardDefinitionEditor": True,
        "hasReloadAll": True,
    }

    await probe.assert_clean()
