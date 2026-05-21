from __future__ import annotations

import logging
from pathlib import Path

from ape_sdk.control.client import ControlApiClient
from ape_sdk.database.migrations.module_migration_runner import ModuleMigrationRunner
from ape_sdk.tenant.database import TenantDatabase

logger = logging.getLogger(__name__)


class TenantModuleMigrationRunner:
    def __init__(
        self,
        *,
        control_api_client: ControlApiClient,
        module_name: str,
        sql_files_path: str | Path,
        manifest_json: str | None = None,
        manifest_path: str | Path | None = None,
        lock_timeout_seconds: int = 30,
    ) -> None:
        self.control_api_client = control_api_client
        self.module_name = module_name
        self.sql_files_path = Path(sql_files_path)
        self.manifest_json = manifest_json
        self.manifest_path = Path(manifest_path) if manifest_path else None
        self.lock_timeout_seconds = lock_timeout_seconds

    def run_for_active_tenants(self) -> None:
        tenant_keys = self.control_api_client.list_active_tenant_keys()
        logger.info(
            "Running module database migrations for active tenants module_name=%s tenant_count=%s",
            self.module_name,
            len(tenant_keys),
        )

        for tenant_key in tenant_keys:
            logger.info(
                "Running module database migrations tenant_key=%s module_name=%s",
                tenant_key,
                self.module_name,
            )
            tenant_context = self.control_api_client.get_worker_context(tenant_key)
            tenant_database = TenantDatabase(tenant_context)
            ModuleMigrationRunner(
                database_connection=tenant_database.get_engine(),
                module_name=self.module_name,
                manifest_json=self.manifest_json,
                manifest_path=self.manifest_path,
                sql_files_path=self.sql_files_path,
                lock_timeout_seconds=self.lock_timeout_seconds,
            ).run()
            logger.info(
                "Completed module database migrations tenant_key=%s module_name=%s",
                tenant_key,
                self.module_name,
            )
