"""
Web UI tests for the Phase F sensitivity dial: the upload form exposes a
"Detection sensitivity" dropdown (broad/standard/precise, default standard),
and the selected mode is visible in the results page header.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

SAMPLE_DIR = Path("data/sample")
_REQUIRED = ["matter_register", "client_ledger", "trust_bank_statement", "reconciliation_summary"]
# Default web config enables R08/R09/R10/R12, which need these too.
_OPTIONAL = ["invoice_register", "allocations"]


@pytest.fixture()
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


def _upload_files() -> dict:
    files = {}
    for name in _REQUIRED + _OPTIONAL:
        content = (SAMPLE_DIR / f"{name}.csv").read_bytes()
        files[name] = (io.BytesIO(content), f"{name}.csv")
    return files


class TestIndexPageSensitivityDropdown:
    def test_index_page_has_sensitivity_select(self, client):
        resp = client.get("/")
        html = resp.get_data(as_text=True)
        assert 'name="sensitivity"' in html
        assert 'value="broad"' in html
        assert 'value="standard"' in html
        assert 'value="precise"' in html

    def test_standard_is_the_default_selected_option(self, client):
        resp = client.get("/")
        html = resp.get_data(as_text=True)
        # crude but robust: the standard <option> carries "selected"
        idx = html.index('value="standard"')
        snippet = html[idx: idx + 40]
        assert "selected" in snippet


class TestResultsPageShowsSensitivity:
    def test_broad_sensitivity_flows_through_to_results_header(self, client):
        data = {
            "firm_name": "Test Firm",
            "review_period": "June 2026",
            "as_at": "2026-06-25",
            "sensitivity": "broad",
            **_upload_files(),
        }
        resp = client.post("/run", data=data, content_type="multipart/form-data",
                            follow_redirects=True)
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Sensitivity: Broad" in html

    def test_omitted_sensitivity_defaults_to_standard_in_results_header(self, client):
        data = {
            "firm_name": "Test Firm",
            "review_period": "June 2026",
            "as_at": "2026-06-25",
            **_upload_files(),
        }
        resp = client.post("/run", data=data, content_type="multipart/form-data",
                            follow_redirects=True)
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Sensitivity: Standard" in html
