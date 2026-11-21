"""Guard the jury-facing dashboard's public-evidence presentation.

These are deterministic frontend contract checks, NOT a browser E2E test.
The full P0 frontend_js_syntax and dashboard API integration are also required.
"""
from importlib.resources import files


def _asset(name):
    return files("ledgergym").joinpath("dashboard_static", name).read_text(encoding="utf-8")


def test_jury_invoice_total_and_core_money_columns_are_visible():
    js = _asset("app.js")
    assert 'invoices: ["invoice_id", "doc_id", "entity_id", "currency", "total_minor"' in js
    assert '"debit_minor", "credit_minor"' in js
    assert '"amount_minor"' in js
    assert "Object.keys(rows[0]).slice(0, 7)" not in js
    assert 'const fields = [...new Set(' in js


def test_jury_evidence_drilldown_never_requests_private_sources():
    js = _asset("app.js")
    assert "async function inspectPublicEvidence(" in js
    assert '"/api/records?"' in js
    assert '["invoices", "payments", "ledger", "fx"]' in js
    assert '"private"' not in js[js.index("async function inspectPublicEvidence("):
                                    js.index("function renderFindings(")]
    assert "document.createElement(tag)" in js
    assert ".innerHTML" not in js


def test_jury_evidence_panel_has_accessible_inspection_controls():
    js = _asset("app.js")
    html = _asset("index.html")
    css = _asset("app.css")
    assert 'id="explorer"' in html
    assert 'button.type = "button"' in js
    assert 'link.type = "button"' in js
    assert 'button.addEventListener("click"' in js
    assert "state.highlightId = id" in js
    assert ".evidence-preview" in css
    assert ".evidence-highlight" in css
