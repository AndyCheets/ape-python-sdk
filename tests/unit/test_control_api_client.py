import json

import pytest
from email_sync_worker.control_api_client import ControlApiClient, ControlApiError


class FakeResponse:
    def __init__(self, status: int, body: dict) -> None:
        self.status = status
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_control_api_sends_bearer_token_and_maps_worker_context(monkeypatch) -> None:
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeResponse(
            200,
            {
                "tenantKey": "bite-demo",
                "displayName": "Bite Demo",
                "databaseName": "ape_tenant_bite_demo_dev",
                "enabledModules": ["email-campaigns"],
                "tenantDatabaseConnectionString": (
                    "Server=mysql;Database=tenant;User Id=ape;Password=secret;"
                ),
            },
        )

    monkeypatch.setattr("email_sync_worker.control_api_client.urlopen", fake_urlopen)

    context = ControlApiClient("http://falcon:5209", "test-token").get_worker_context("bite-demo")

    assert calls[0][0].full_url == "http://falcon:5209/control/tenants/bite-demo/worker-context"
    assert calls[0][0].headers["Authorization"] == "Bearer test-token"
    assert context.tenant_key == "bite-demo"
    assert context.tenant_database_connection_string.startswith("Server=mysql")


def test_control_api_non_200_response_is_clear(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return FakeResponse(500, {"error": "nope"})

    monkeypatch.setattr("email_sync_worker.control_api_client.urlopen", fake_urlopen)

    with pytest.raises(ControlApiError, match="HTTP 500"):
        ControlApiClient("http://falcon:5209", "test-token").get_worker_context("bite-demo")


def test_control_api_token_is_not_logged(monkeypatch, caplog) -> None:
    def fake_urlopen(request, timeout):
        return FakeResponse(500, {"error": "nope"})

    monkeypatch.setattr("email_sync_worker.control_api_client.urlopen", fake_urlopen)

    with pytest.raises(ControlApiError):
        ControlApiClient("http://falcon:5209", "secret-token").get_worker_context("bite-demo")

    assert "secret-token" not in caplog.text
