from __future__ import annotations

import re
from pathlib import Path
from zipfile import ZipFile

import pytest
from _asset_inventory import active_patchhub_main_paths
from _browser_probe import BrowserProbe
from playwright.async_api import Page, expect

pytestmark = pytest.mark.only_browser("chromium")
REPO_ROOT = Path(__file__).resolve().parents[2]


async def _wait_for_patchhub_boot(page: Page) -> None:
    await page.wait_for_function(
        """
        () => (
          typeof window.validateAndPreview === "function" &&
          !!window.AMP_PATCHHUB_UI &&
          typeof window.AMP_PATCHHUB_UI.saveLiveJobId === "function" &&
          typeof window.AMP_PATCHHUB_UI.getLiveJobId === "function" &&
          typeof window.AMP_PATCHHUB_UI.updateProgressPanelFromEvents ===
            "function"
        )
        """
    )


def _write_pm_zip(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w") as zf:
        zf.writestr("COMMIT_MESSAGE.txt", "PatchHub E2E subset\n")
        zf.writestr("ISSUE_NUMBER.txt", "510\n")
        zf.writestr(
            "patches/per_file/scripts__patchhub__app_api_jobs.py.patch",
            "--- a/x\n+++ b/x\n",
        )
        zf.writestr(
            "patches/per_file/scripts__patchhub__models.py.patch",
            "--- a/x\n+++ b/x\n",
        )
        zf.writestr(
            "patches/per_file/scripts__patchhub__static__app.js.patch",
            "--- a/x\n+++ b/x\n",
        )
        zf.writestr(
            "patches/per_file/tests__test_patchhub_zip_subset_ui_contract.py.patch",
            "--- a/x\n+++ b/x\n",
        )


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


@pytest.mark.asyncio(loop_scope="session")
async def test_patchhub_zip_subset_modal_uses_apply_and_blue_theme(
    page: Page,
    e2e_patchhub_base_url: str,
) -> None:
    patch_path = REPO_ROOT / "patches" / "issue_510_e2e_subset.zip"
    _write_pm_zip(patch_path)

    response = await page.goto(f"{e2e_patchhub_base_url}/", wait_until="domcontentloaded")
    assert response is not None and response.ok
    await _wait_for_patchhub_boot(page)

    await page.locator("#issueId").fill("510")
    await page.locator("#commitMsg").fill("PatchHub E2E subset")
    await page.locator("#patchPath").fill("patches/issue_510_e2e_subset.zip")
    await page.evaluate("window.validateAndPreview()")

    strip = page.locator("#zipSubsetStrip")
    await expect(strip).to_contain_text("ZIP patch detected: 4 target files")
    await expect(strip).to_contain_text("Using uploaded zip (4 files)")

    await page.locator("#zipSubsetOpenBtn").click()
    await expect(page.locator("#zipSubsetModalTitle")).to_have_text("Select target files (4)")
    await expect(page.locator("#zipSubsetModalSubtitle")).to_have_text(
        "Contents of issue_510_e2e_subset.zip"
    )
    await expect(page.locator("#zipSubsetApplyBtn")).to_be_visible()

    modal_bg = await page.locator(".zip-subset-modal-card").evaluate(
        "(node) => window.getComputedStyle(node).backgroundColor"
    )
    assert modal_bg == "rgb(18, 31, 59)"

    first_check = page.locator(".zip-subset-check").first
    await first_check.uncheck()
    await expect(page.locator("#zipSubsetSelectionCount")).to_have_text("Selected 3 / 4")
    await expect(strip).to_contain_text("Using uploaded zip (4 files)")

    await page.locator("#zipSubsetCancelBtn").click()
    await expect(strip).to_contain_text("Using uploaded zip (4 files)")

    await page.locator("#zipSubsetOpenBtn").click()
    await page.locator(".zip-subset-check").first.uncheck()
    await page.locator("#zipSubsetApplyBtn").click()
    await expect(strip).to_contain_text("Selected 3 / 4 files")

    await page.locator("#zipSubsetOpenBtn").click()
    await page.locator("#zipSubsetClearBtn").click()
    await expect(page.locator("#zipSubsetSelectionCount")).to_have_text("Selected 0 / 4")
    await page.locator("#zipSubsetApplyBtn").click()
    await expect(page.locator("#enqueueBtn")).to_be_disabled()


@pytest.mark.asyncio(loop_scope="session")
async def test_patchhub_progress_renders_applied_files_from_job_detail(
    page: Page,
    e2e_patchhub_base_url: str,
) -> None:
    response = await page.goto(f"{e2e_patchhub_base_url}/", wait_until="domcontentloaded")
    assert response is not None and response.ok
    await _wait_for_patchhub_boot(page)

    await page.evaluate(
        """
        () => {
          const originalFetch = window.fetch.bind(window);
          window.fetch = (input, init) => {
            const url = typeof input === "string" ? input : String(input.url || "");
            if (url.endsWith("/api/jobs/e2e-job")) {
              return Promise.resolve(
                new Response(
                  JSON.stringify({
                    ok: true,
                    job: {
                      job_id: "e2e-job",
                      applied_files: [
                        "scripts/patchhub/static/app_part_zip_subset.js",
                        "tests/test_patchhub_zip_subset_ui_contract.py"
                      ]
                    }
                  }),
                  {
                    status: 200,
                    headers: {"Content-Type": "application/json"}
                  }
                )
              );
            }
            return originalFetch(input, init);
          };
          const ui = window.AMP_PATCHHUB_UI;
          window.localStorage.setItem("amp.liveJobId", "e2e-job");
          ui.saveLiveJobId("e2e-job");
          ui.liveEvents = [
            {type: "log", kind: "DO", stage: "PATCH_APPLY"},
            {type: "log", kind: "OK", stage: "PATCH_APPLY"},
            {type: "result", ok: true}
          ];
        }
        """
    )
    await page.evaluate(
        """
        () => {
          window.AMP_PATCHHUB_UI.updateProgressPanelFromEvents();
        }
        """
    )

    applied = page.locator("#progressApplied")
    await expect(applied).to_contain_text("Applied files (2)")
    await expect(applied).to_contain_text("scripts/patchhub/static/app_part_zip_subset.js")
    await expect(applied).to_contain_text("tests/test_patchhub_zip_subset_ui_contract.py")
