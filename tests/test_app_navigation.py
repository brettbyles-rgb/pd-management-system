from pathlib import Path
import subprocess
import sys


PACKAGE_DIR = Path(__file__).parents[1] / "src" / "pd_extractor"
INTELLIGENCE_APP_SOURCE = (PACKAGE_DIR / "intelligence_app.py").read_text(encoding="utf-8")
VALIDATION_APP_SOURCE = (PACKAGE_DIR / "validation_app.py").read_text(encoding="utf-8")


def test_main_shell_keeps_workflows_separate_and_routes_mapping_to_new_ui():
    expected_links = [
        "Career Explorer",
        "Upload",
        "Validation Queue",
        "Role Library",
        "Semantic Search",
        "Mapping Assistant",
        "Classification Admin",
        "Mapping Workbook Import",
    ]

    for label in expected_links:
        assert label in INTELLIGENCE_APP_SOURCE

    assert "<section id=upload class=view>" in INTELLIGENCE_APP_SOURCE
    assert "<section id=mapping class=view>" in INTELLIGENCE_APP_SOURCE
    assert "<section id=workbook class=view>" in INTELLIGENCE_APP_SOURCE
    assert "Download current workbook" in INTELLIGENCE_APP_SOURCE
    assert "Validate workbook" in INTELLIGENCE_APP_SOURCE
    assert "Apply validated workbook" in INTELLIGENCE_APP_SOURCE
    assert "window.location.href='/mapping-assistant?pd=${r.id}'" in INTELLIGENCE_APP_SOURCE
    assert "showView('import')" not in INTELLIGENCE_APP_SOURCE
    assert "showView('admin')" not in INTELLIGENCE_APP_SOURCE


def test_separate_workflows_share_navigation_destinations():
    for html in (INTELLIGENCE_APP_SOURCE, VALIDATION_APP_SOURCE):
        assert "#upload" in html
        assert "Validation Queue" in html
        assert "#library" in html
        assert "mapping-assistant" in html
        assert "Classification Admin" in html
        assert "#workbook" in html


def test_joined_shell_links_explorer_and_replaces_local_validation_navigation():
    assert 'href="/career-explorer"' in INTELLIGENCE_APP_SOURCE
    assert 'href="/validation"' in INTELLIGENCE_APP_SOURCE
    assert "<section id=semantic class=view>" in INTELLIGENCE_APP_SOURCE
    assert "127.0.0.1:8765" not in INTELLIGENCE_APP_SOURCE[INTELLIGENCE_APP_SOURCE.index("HTML_V2 ="):INTELLIGENCE_APP_SOURCE.index("ADMIN_HTML =")]


def test_intelligence_app_module_can_reach_its_command_line_parser():
    result = subprocess.run(
        [sys.executable, "-m", "pd_extractor.intelligence_app", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Run the local PD role intelligence app" in result.stdout
