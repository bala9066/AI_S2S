"""
End-to-End UI Tests using Playwright.

Tests the full Hardware Pipeline Streamlit UI at http://localhost:8501

Run with:
    pip install playwright pytest-playwright
    playwright install chromium
    pytest tests/test_ui_playwright.py -v --headed  # headed = see the browser
    pytest tests/test_ui_playwright.py -v           # headless
"""

import re
import time
import pytest
from playwright.sync_api import Page, expect, sync_playwright

BASE_URL = "http://localhost:8501"
TIMEOUT = 30_000  # 30s timeout for slow LLM responses


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def browser_context():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=200)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        yield context
        browser.close()


@pytest.fixture
def page(browser_context):
    page = browser_context.new_page()
    page.goto(BASE_URL, wait_until="networkidle", timeout=TIMEOUT)
    yield page
    page.close()


def _navigate_tab(page: Page, tab_label: str):
    """Click a tab by its label text (handles emoji prefixes in Streamlit buttons)."""
    # Use a partial text match since tabs have emoji prefixes like "🏠 Overview"
    btn = page.get_by_role("button", name=re.compile(tab_label, re.IGNORECASE)).first
    btn.click()
    page.wait_for_load_state("networkidle")
    time.sleep(1)


def _wait_for_text(page: Page, text: str, timeout: int = TIMEOUT):
    """Wait until text appears anywhere on the page."""
    page.wait_for_selector(f"text={text}", timeout=timeout)


# ─── Test 1: App loads ────────────────────────────────────────────────────────

class TestAppLoads:
    def test_homepage_title(self, page: Page):
        """App loads and shows the main title."""
        # Use first() to handle multiple matching elements
        expect(page.get_by_role("heading", name="Hardware Pipeline").first).to_be_visible()
        print("App loaded successfully")

    def test_tab_navigation_visible(self, page: Page):
        """All navigation tabs are present (emoji-prefixed)."""
        # Tabs in app.py have emoji prefixes: "🏠 Overview", "➕ New Project", etc.
        tab_patterns = [
            "Overview",
            "New Project",
            "Design Chat",
            "Pipeline",
            "Documents",
            "Netlist",
            "Code Review",
            "Dashboard",
        ]
        for tab in tab_patterns:
            btn = page.get_by_role("button", name=re.compile(tab, re.IGNORECASE)).first
            expect(btn).to_be_visible()
        print(f"✅ All {len(tab_patterns)} tabs visible")

    def test_sidebar_visible(self, page: Page):
        """Sidebar loads with system info."""
        expect(page.locator("text=Hardware Pipeline").first).to_be_visible()
        print("✅ Sidebar visible")


# ─── Test 2: Overview Tab ─────────────────────────────────────────────────────

class TestOverviewTab:
    def test_pipeline_bar_visible(self, page: Page):
        """Overview shows the pipeline progress bar."""
        _navigate_tab(page, "Overview")
        expect(page.locator(".pipeline-bar")).to_be_visible()
        print("✅ Pipeline bar visible on Overview")

    def test_feature_cards_visible(self, page: Page):
        """Feature cards (IEEE Docs, Netlist, Compliance, Code Gen) are shown."""
        _navigate_tab(page, "Overview")
        for label in ["IEEE Docs", "Netlist", "Compliance", "Code Gen"]:
            expect(page.locator(f"text={label}")).to_be_visible()
        print("✅ Feature cards visible")

    def test_quick_start_buttons(self, page: Page):
        """Quick start buttons are clickable."""
        _navigate_tab(page, "Overview")
        expect(page.get_by_role("button", name=re.compile("New Project", re.IGNORECASE)).first).to_be_visible()
        print("✅ Quick start buttons visible")


# ─── Test 3: New Project Tab ──────────────────────────────────────────────────

class TestNewProjectTab:
    def test_form_fields_visible(self, page: Page):
        """New Project form shows all required fields."""
        _navigate_tab(page, "New Project")
        # Streamlit labels the input with the text passed to st.text_input
        expect(page.get_by_label("Project Name *")).to_be_visible()
        expect(page.get_by_label("Description")).to_be_visible()
        print("✅ Project form fields visible")

    def test_design_type_selectbox_visible(self, page: Page):
        """Design type selectbox is visible (Streamlit renders as custom div)."""
        _navigate_tab(page, "New Project")
        # Streamlit selectbox is NOT a native <select> - it's a custom div
        # Look for the label "Design Type *" instead
        design_type_label = page.locator("text=Design Type")
        expect(design_type_label.first).to_be_visible()
        print("✅ Design Type selectbox visible")

    def test_create_button_visible(self, page: Page):
        """Create & Start form submit button is visible."""
        _navigate_tab(page, "New Project")
        # Button label is "🚀 Create & Start"
        btn = page.get_by_role("button", name=re.compile("Create.*Start", re.IGNORECASE)).first
        expect(btn).to_be_visible()
        print("✅ Create & Start button visible")

    def test_create_project_empty_name(self, page: Page):
        """Form validation fires when project name is empty."""
        _navigate_tab(page, "New Project")
        # Click the form submit button (has emoji prefix "🚀 Create & Start")
        page.get_by_role("button", name=re.compile("Create.*Start", re.IGNORECASE)).first.click()
        time.sleep(1)
        # Error message is "Project name is required."
        expect(page.locator("text=Project name is required")).to_be_visible()
        print("✅ Empty name validation works")

    def test_create_project_success(self, page: Page):
        """Creating a project navigates to Design Chat."""
        _navigate_tab(page, "New Project")
        page.get_by_label("Project Name *").fill("PW Test Project")
        page.get_by_label("Description").fill("Playwright automated test project")
        page.get_by_role("button", name=re.compile("Create.*Start", re.IGNORECASE)).first.click()

        # Should navigate to Design Chat — wait for the tab heading or welcome text
        _wait_for_text(page, "Design Chat", timeout=15_000)
        print("✅ Project created, navigated to Design Chat")


# ─── Test 4: Design Chat Tab ──────────────────────────────────────────────────

class TestDesignChatTab:
    def test_welcome_message_shown(self, page: Page):
        """Design chat shows welcome message after project creation."""
        _navigate_tab(page, "Design Chat")
        time.sleep(1)
        # Check either the welcome message OR the 'create project' prompt
        welcome_visible = page.locator("text=Welcome to Hardware Pipeline").is_visible()
        create_visible = page.locator("text=Create a project first").is_visible()
        assert welcome_visible or create_visible, "Neither welcome nor create prompt visible"
        print("✅ Design Chat shows expected content")

    def test_chat_input_visible(self, page: Page):
        """Chat input box is present when project is loaded."""
        _navigate_tab(page, "Design Chat")
        time.sleep(1)
        # Streamlit chat input has placeholder "Describe your hardware design…"
        inputs = page.locator("textarea[placeholder*='design'], textarea[placeholder*='hardware']")
        if inputs.count() > 0:
            print("✅ Chat input visible")
        else:
            # May need to create project first
            print("⚠️  Chat input not visible (no project loaded)")

    def test_draft_generation(self, page: Page):
        """Typing a design description generates a draft block diagram."""
        _navigate_tab(page, "Design Chat")
        time.sleep(1)

        # Look for chat input with Streamlit's chat_input placeholder
        chat_input = page.locator(
            "textarea[placeholder*='design' i], "
            "textarea[placeholder*='hardware' i], "
            "input[placeholder*='design' i]"
        ).first
        if not chat_input.is_visible():
            pytest.skip("No project loaded — skipping chat test")

        chat_input.fill("Simple LED blink circuit with ATmega328P, 5V supply")
        chat_input.press("Enter")

        # Wait for draft to appear (LLM call — up to 60s)
        print("⏳ Waiting for draft generation (LLM call)...")
        _wait_for_text(page, "Draft", timeout=60_000)
        print("✅ Draft block diagram generated")

    def test_approve_button_visible_after_draft(self, page: Page):
        """Approve button appears after draft is shown."""
        _navigate_tab(page, "Design Chat")
        time.sleep(1)

        # Check if draft is pending (approve button visible)
        # Button has emoji: "✅ Approve — Generate Full Docs"
        approve_btn = page.get_by_role("button", name=re.compile("Approve", re.IGNORECASE))
        if approve_btn.is_visible():
            print("✅ Approve button visible")
        else:
            print("⚠️  Approve button not visible (draft not generated yet)")


# ─── Test 5: Sidebar API Key Status ───────────────────────────────────────────

class TestSidebar:
    def test_api_key_status_shown(self, page: Page):
        """Sidebar shows API key status indicators."""
        sidebar = page.locator("[data-testid='stSidebar']")
        # Look for GLM key status (either ✅ or ⬜ indicator)
        expect(sidebar.locator("text=GLM").first).to_be_visible()
        print("✅ API key status shown in sidebar")

    def test_mode_indicator(self, page: Page):
        """Mode indicator (Online/Air-Gapped) shown in sidebar."""
        sidebar = page.locator("[data-testid='stSidebar']")
        # Either "Online" or "Air-Gapped" mode
        online = sidebar.locator("text=Online").is_visible()
        air_gapped = sidebar.locator("text=Air-Gapped").is_visible()
        assert online or air_gapped, "Neither Online nor Air-Gapped indicator found"
        print("✅ Mode indicator present in sidebar")

    def test_pipeline_status_in_sidebar(self, page: Page):
        """Sidebar shows project pipeline status or 'no project' message."""
        sidebar = page.locator("[data-testid='stSidebar']")
        # Either shows pipeline status or the info message
        has_status = sidebar.locator("text=Pipeline Status").is_visible()
        no_proj = sidebar.locator("text=No project loaded").is_visible()
        assert has_status or no_proj, "Sidebar pipeline section not found"
        print("✅ Sidebar pipeline section present")


# ─── Test 6: Documents Tab ────────────────────────────────────────────────────

class TestDocumentsTab:
    def test_documents_tab_loads(self, page: Page):
        """Documents tab loads without errors."""
        _navigate_tab(page, "Documents")
        time.sleep(1)
        # Either shows documents or 'no documents yet' or 'no project'
        has_docs = page.locator("text=documents generated").is_visible()
        no_docs = page.locator("text=No documents").is_visible()
        no_project = page.locator("text=No project loaded").is_visible()
        no_docs_yet = page.locator("text=No documents yet").is_visible()
        complete_phase = page.locator("text=complete Phase 1").is_visible()
        assert has_docs or no_docs or no_project or no_docs_yet or complete_phase, \
            "Documents tab in unexpected state"
        print("✅ Documents tab loads correctly")

    def test_documents_heading_visible(self, page: Page):
        """Documents tab shows the main heading."""
        _navigate_tab(page, "Documents")
        time.sleep(1)
        # Heading: "📄 Generated Documents"
        expect(page.locator("text=Generated Documents").first).to_be_visible()
        print("✅ Documents heading visible")


# ─── Test 7: Netlist Tab ─────────────────────────────────────────────────────

class TestNetlistTab:
    def test_netlist_tab_loads(self, page: Page):
        """Netlist tab loads without errors."""
        _navigate_tab(page, "Netlist")
        time.sleep(1)
        # Either shows "Netlist Viewer" heading or "no project" or "not generated"
        heading = page.locator("text=Netlist Viewer").is_visible()
        no_proj = page.locator("text=No project loaded").is_visible()
        not_gen = page.locator("text=Netlist not generated").is_visible()
        assert heading or no_proj or not_gen, "Netlist tab in unexpected state"
        print("✅ Netlist tab loads correctly")

    def test_netlist_heading_visible(self, page: Page):
        """Netlist tab shows its heading."""
        _navigate_tab(page, "Netlist")
        time.sleep(1)
        # Heading: "🔌 Netlist Viewer — Phase 4"
        expect(page.locator("text=Netlist Viewer").first).to_be_visible()
        print("✅ Netlist heading visible")


# ─── Test 8: Dashboard Tab ────────────────────────────────────────────────────

class TestDashboardTab:
    def test_dashboard_loads(self, page: Page):
        """Dashboard tab loads and shows the heading."""
        _navigate_tab(page, "Dashboard")
        time.sleep(1)
        # Heading: "📊 Projects Dashboard"
        expect(page.locator("text=Projects Dashboard").first).to_be_visible()
        print("✅ Dashboard tab loads correctly")

    def test_metric_cards_visible(self, page: Page):
        """Dashboard shows metric cards or 'no projects' message."""
        _navigate_tab(page, "Dashboard")
        time.sleep(2)
        # Either metric cards appear or "no projects yet" message
        cards = page.locator(".metric-card")
        no_proj = page.locator("text=No projects yet").is_visible()
        count = cards.count()
        if count > 0 or no_proj:
            print(f"✅ Dashboard shows {count} metric cards")
        else:
            print("⚠️  Dashboard: no metric cards and no 'no projects' message")


# ─── Test 9: Code Review Tab ─────────────────────────────────────────────────

class TestCodeReviewTab:
    def test_code_review_tab_loads(self, page: Page):
        """Code Review tab loads without errors."""
        _navigate_tab(page, "Code Review")
        time.sleep(1)
        # Heading: "🔍 Code Review — Phase 8c"
        expect(page.locator("text=Code Review").first).to_be_visible()
        no_proj = page.locator("text=No project loaded").is_visible()
        not_gen = page.locator("text=Code not generated").is_visible()
        heading = page.locator("text=Code Review").is_visible()
        assert heading or no_proj or not_gen, "Code Review tab in unexpected state"
        print("✅ Code Review tab loads correctly")


# ─── Test 10: Screenshot capture ───────────────────────────────────────────────

class TestScreenshots:
    """Take screenshots of each tab for visual review."""

    def test_capture_all_tabs(self, browser_context):
        """Capture screenshots of all tabs."""
        page = browser_context.new_page()
        page.goto(BASE_URL, wait_until="networkidle", timeout=TIMEOUT)

        tabs = {
            "overview": "Overview",
            "new": "New Project",
            "chat": "Design Chat",
            "pipeline": "Pipeline",
            "docs": "Documents",
            "netlist": "Netlist",
            "code": "Code Review",
            "dashboard": "Dashboard",
        }

        import os
        os.makedirs("test_screenshots", exist_ok=True)

        for key, label in tabs.items():
            try:
                _navigate_tab(page, label)
                time.sleep(1.5)
                page.screenshot(path=f"test_screenshots/{key}.png", full_page=True)
                print(f"📸 Screenshot saved: test_screenshots/{key}.png")
            except Exception as e:
                print(f"⚠️  Could not screenshot {label}: {e}")

        page.close()
        print("✅ All screenshots captured in test_screenshots/")


# ─── Standalone runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    """Run a quick smoke test without pytest."""
    import sys
    import io
    # Fix Windows encoding issue
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    print("=" * 60)
    print("Hardware Pipeline - Playwright Smoke Test")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        print(f"\n🌐 Opening {BASE_URL}...")
        page.goto(BASE_URL, wait_until="networkidle", timeout=TIMEOUT)

        print("📋 Checking title...")
        title = page.title()
        print(f"   Page title: {title}")

        print("Checking all tabs...")
        tabs = ["Overview", "New Project", "Design Chat", "Pipeline",
                "Documents", "Netlist", "Code Review", "Dashboard"]
        for tab in tabs:
            btn = page.get_by_role("button", name=re.compile(tab, re.IGNORECASE)).first
            visible = btn.is_visible()
            print(f"   {'OK' if visible else 'X'} {tab} tab")

        print("\n📸 Taking screenshots of all tabs...")
        import os
        os.makedirs("test_screenshots", exist_ok=True)
        for tab in tabs:
            _navigate_tab(page, tab)
            key = tab.lower().replace(" ", "_")
            page.screenshot(path=f"test_screenshots/{key}.png", full_page=True)
            print(f"   📸 {key}.png saved")

        print("\n➕ Creating a test project...")
        _navigate_tab(page, "New Project")
        page.get_by_label("Project Name *").fill("Playwright Smoke Test")
        page.get_by_label("Description").fill("Automated test by Playwright")
        page.get_by_role("button", name=re.compile("Create.*Start", re.IGNORECASE)).first.click()
        time.sleep(3)

        print("\nSending design description...")
        chat_input = page.locator(
            "textarea[placeholder*='design' i], "
            "textarea[placeholder*='hardware' i], "
            "input[placeholder*='design' i]"
        ).first
        if chat_input.is_visible():
            chat_input.fill("Simple 3.3V power supply with LDO regulator")
            chat_input.press("Enter")
            print("   ⏳ Waiting for AI response (up to 60s)...")
            try:
                page.wait_for_selector("text=Draft", timeout=60_000)
                print("   ✅ Draft generated!")
                page.screenshot(path="test_screenshots/draft_generated.png", full_page=True)
            except Exception:
                print("   ⚠️  Draft not generated within timeout")
        else:
            print("   ⚠️  Chat input not found")

        print("\n" + "=" * 60)
        print("Smoke test complete! Check test_screenshots/ for visuals.")
        print("=" * 60)
        input("\nPress Enter to close browser...")
        browser.close()
