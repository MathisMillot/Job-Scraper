import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_search_source_display_and_save_modal(page, live_server):
    page.goto(live_server)

    expect(page.locator("#atsSlugsGroup")).to_be_hidden()
    page.locator('input[name="sources"][value="greenhouse"]').check()
    expect(page.locator("#atsSlugsGroup")).to_be_visible()
    page.locator("#slugInput").fill("example")
    page.locator("#slugInput").press("Enter")

    page.locator("#keywordInput").fill("python")
    page.locator("#keywordInput").press("Enter")
    page.locator("#searchForm .btn").click()

    expect(page.locator(".source-wttj")).to_contain_text("WTTJ")
    save_button = page.locator(".btn-save").first
    save_button.click()
    expect(page.locator("#labelModal")).to_be_visible()
    page.locator("#labelInput").fill("Favorite")
    page.locator("#labelConfirmBtn").click()
    expect(save_button).to_have_text("Sauvegardé")
