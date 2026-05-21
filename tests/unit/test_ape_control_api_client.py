import json

import pytest
from ape_sdk.control import client as control_client_module
from ape_sdk.control.client import ControlApiClient
from ape_sdk.worker.errors import ControlApiError


class FakeResponse:
    def __init__(self, status: int, body) -> None:  # type: ignore[no-untyped-def]
        self.status = status
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # type: ignore[no-untyped-def]
        return None

    def read(self) -> bytes:
        return self.body


def test_list_active_tenant_keys_parses_tenant_objects(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        calls.append((request, timeout))
        return FakeResponse(
            200,
            {
                "tenants": [
                    {"tenantKey": "tenant-a"},
                    {"tenantKey": "tenant-b"},
                ]
            },
        )

    monkeypatch.setattr(control_client_module, "urlopen", fake_urlopen)

    tenant_keys = ControlApiClient(
        base_url="http://control-api",
        token="control-token-secret",
        timeout_seconds=3,
    ).list_active_tenant_keys()

    assert tenant_keys == ["tenant-a", "tenant-b"]
    assert calls[0][0].full_url == "http://control-api/control/tenants"
    assert calls[0][0].headers["Authorization"] == "Bearer control-token-secret"


def test_list_active_tenant_keys_parses_control_api_results_shape(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        return FakeResponse(
            200,
            {
                "count": 2,
                "results": [
                    {
                        "tenantKey": "bite-demo",
                        "displayName": "Bite Demo",
                        "isActive": True,
                        "databaseName": "ape_tenant_bite_demo_dev",
                        "enabledModules": ["email-campaigns", "sample"],
                    },
                    {
                        "tenantKey": "sswc",
                        "displayName": "South Shields Westoe Club",
                        "isActive": True,
                        "databaseName": "ape_tenant_sswc_dev",
                        "enabledModules": ["email-campaigns", "events", "sample"],
                    },
                ],
            },
        )

    monkeypatch.setattr(control_client_module, "urlopen", fake_urlopen)

    tenant_keys = ControlApiClient(
        base_url="http://control-api",
        token="control-token-secret",
        timeout_seconds=3,
    ).list_active_tenant_keys()

    assert tenant_keys == ["bite-demo", "sswc"]


def test_list_active_tenant_keys_skips_inactive_result_entries(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        return FakeResponse(
            200,
            {
                "count": 2,
                "results": [
                    {"tenantKey": "active-tenant", "isActive": True},
                    {"tenantKey": "inactive-tenant", "isActive": False},
                ],
            },
        )

    monkeypatch.setattr(control_client_module, "urlopen", fake_urlopen)

    tenant_keys = ControlApiClient(
        base_url="http://control-api",
        token="control-token-secret",
        timeout_seconds=3,
    ).list_active_tenant_keys()

    assert tenant_keys == ["active-tenant"]


def test_list_active_tenant_keys_parses_string_list(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        return FakeResponse(200, ["tenant-a", "tenant-b"])

    monkeypatch.setattr(control_client_module, "urlopen", fake_urlopen)

    tenant_keys = ControlApiClient(
        base_url="http://control-api",
        token="control-token-secret",
        timeout_seconds=3,
    ).list_active_tenant_keys()

    assert tenant_keys == ["tenant-a", "tenant-b"]


def test_list_active_tenant_keys_rejects_invalid_payload(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        return FakeResponse(200, {"notTenants": []})

    monkeypatch.setattr(control_client_module, "urlopen", fake_urlopen)

    with pytest.raises(ControlApiError, match="invalid active tenants response"):
        ControlApiClient(
            base_url="http://control-api",
            token="control-token-secret",
            timeout_seconds=3,
        ).list_active_tenant_keys()
