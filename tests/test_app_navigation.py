from pathlib import Path


PACKAGE_DIR = Path(__file__).parents[1] / "src" / "pd_extractor"
INTELLIGENCE_APP_SOURCE = (PACKAGE_DIR / "intelligence_app.py").read_text(encoding="utf-8")
VALIDATION_APP_SOURCE = (PACKAGE_DIR / "validation_app.py").read_text(encoding="utf-8")


def test_main_shell_keeps_workflows_separate_and_routes_mapping_to_new_ui():
    expected_links = [
        "Upload",
        "Validation Queue",
        "Search",
        "Mapping Assistant",
        "Classification Admin",
        "Mapping Workbook Import",
    ]

    for label in expected_links:
        assert label in INTELLIGENCE_APP_SOURCE

    assert "<section id=upload class=view>" in INTELLIGENCE_APP_SOURCE
    assert "<section id=mapping class=view>" in INTELLIGENCE_APP_SOURCE
    assert "<section id=workbook class=view>" in INTELLIGENCE_APP_SOURCE
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
