import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import ValidationError

from ape_sdk.tenant.context import TenantWorkerContext
from ape_sdk.worker.errors import ControlApiError


@dataclass(frozen=True)
class ControlApiClient:
    base_url: str
    token: str
    timeout_seconds: float = 10.0

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
