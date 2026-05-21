import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import ValidationError

from ape_sdk.control.errors import ControlApiError
from ape_sdk.tenant.context import TenantWorkerContext


@dataclass(frozen=True)
class ControlApiClient:
    base_url: str
    token: str
    timeout_seconds: float = 10.0

    def list_active_tenant_keys(self) -> list[str]:
        url = f"{self.base_url.rstrip('/')}/control/tenants"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status = response.status
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise ControlApiError(
                f"Control API returned HTTP {exc.code} for active tenant discovery"
            ) from exc
        except URLError as exc:
            raise ControlApiError("Control API request failed for active tenant discovery") from exc

        if status < 200 or status >= 300:
            raise ControlApiError(f"Control API returned HTTP {status} for active tenant discovery")

        try:
            payload: Any = json.loads(body)
            return _parse_active_tenant_keys(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ControlApiError(
                "Control API returned an invalid active tenants response"
            ) from exc

    def get_worker_context(self, tenant_key: str) -> TenantWorkerContext:
        safe_tenant_key = quote(tenant_key, safe="")
        url = f"{self.base_url.rstrip('/')}/control/tenants/{safe_tenant_key}/worker-context"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status = response.status
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise ControlApiError(
                f"Control API returned HTTP {exc.code} for tenant worker context"
            ) from exc
        except URLError as exc:
            raise ControlApiError("Control API request failed for tenant worker context") from exc

        if status < 200 or status >= 300:
            raise ControlApiError(f"Control API returned HTTP {status} for tenant worker context")

        try:
            payload: dict[str, Any] = json.loads(body)
            return TenantWorkerContext.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ControlApiError(
                "Control API returned an invalid worker context response"
            ) from exc


def _parse_active_tenant_keys(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        raw_tenants = payload.get("results", payload.get("tenants"))
    else:
        raw_tenants = payload

    if not isinstance(raw_tenants, list):
        raise ValueError(
            "active tenants response must be a list or contain a results list"
        )

    tenant_keys: list[str] = []
    for item in raw_tenants:
        if isinstance(item, str):
            tenant_key = item.strip()
        elif isinstance(item, dict):
            if item.get("isActive") is False:
                continue
            raw_key = item.get("tenantKey") or item.get("tenant_key") or item.get("key")
            tenant_key = str(raw_key or "").strip()
        else:
            raise ValueError("active tenant entries must be strings or objects")

        if not tenant_key:
            raise ValueError("active tenant entry is missing tenantKey")
        tenant_keys.append(tenant_key)

    return tenant_keys
