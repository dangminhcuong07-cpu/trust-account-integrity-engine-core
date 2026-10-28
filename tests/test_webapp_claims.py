"""The web pages must not make claims that are false where they run.

- On the hosted demo (TRUSTSENTRY_DEMO=true) the server receives uploads, so
  "your data never leaves this machine" is false there.
- R14 is skipped when the input has no reconciliation date, so the form must
  not promise that "all 13 rules always run".
- The New Zealand Law Society does not endorse the tool; no footer may imply it.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


def test_demo_mode_does_not_claim_data_stays_local(client, monkeypatch):
    monkeypatch.setenv("TRUSTSENTRY_DEMO", "true")
    html = client.get("/").get_data(as_text=True)
    assert "never leaves this machine" not in html
    assert "synthetic data only" in html.lower()


def test_local_mode_keeps_the_local_claim(client, monkeypatch):
    monkeypatch.delenv("TRUSTSENTRY_DEMO", raising=False)
    html = client.get("/").get_data(as_text=True)
    assert "never leaves this machine" in html


def test_form_does_not_promise_every_rule_runs(client):
    html = client.get("/").get_data(as_text=True)
    assert "always run" not in html
    assert "not evaluated" in html


def test_no_page_implies_law_society_endorsement():
    import app as app_module
    for template in (app_module.INDEX_HTML, app_module.RESULTS_HTML):
        assert "NZ Law Society compliance" not in template
    assert "Not affiliated with or endorsed by the New Zealand Law Society" in app_module.RESULTS_HTML
