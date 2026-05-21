from __future__ import annotations

from ape_sdk.database.migrations import tenant_module_migration_runner
from ape_sdk.database.migrations.tenant_module_migration_runner import TenantModuleMigrationRunner
from ape_sdk.tenant.context import TenantWorkerContext


def test_tenant_module_runner_runs_migrations_for_active_tenants(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    control_api_client = FakeControlApiClient(["tenant-a", "tenant-b"])
    tenant_databases: list[FakeTenantDatabase] = []
    migration_calls = []

    def fake_tenant_database(tenant_context):  # type: ignore[no-untyped-def]
        database = FakeTenantDatabase(tenant_context.tenant_key)
        tenant_databases.append(database)
        return database

    class FakeModuleMigrationRunner:
        def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
            migration_calls.append(kwargs)

        def run(self) -> None:
            return None

    monkeypatch.setattr(tenant_module_migration_runner, "TenantDatabase", fake_tenant_database)
    monkeypatch.setattr(
        tenant_module_migration_runner,
        "ModuleMigrationRunner",
        FakeModuleMigrationRunner,
    )

    TenantModuleMigrationRunner(
        control_api_client=control_api_client,  # type: ignore[arg-type]
        module_name="ecom-sync",
        manifest_path=tmp_path / "migration-manifest.json",
        sql_files_path=tmp_path,
    ).run_for_active_tenants()

    assert control_api_client.requested_worker_contexts == ["tenant-a", "tenant-b"]
    assert [database.tenant_key for database in tenant_databases] == ["tenant-a", "tenant-b"]
    assert len(migration_calls) == 2
    assert migration_calls[0]["module_name"] == "ecom-sync"
    assert migration_calls[0]["database_connection"] == "engine-tenant-a"


class FakeControlApiClient:
    def __init__(self, tenant_keys: list[str]) -> None:
        self.tenant_keys = tenant_keys
        self.requested_worker_contexts: list[str] = []

    def list_active_tenant_keys(self) -> list[str]:
        return self.tenant_keys

    def get_worker_context(self, tenant_key: str) -> TenantWorkerContext:
        self.requested_worker_contexts.append(tenant_key)
        return TenantWorkerContext(
            tenantKey=tenant_key,
            displayName=tenant_key,
            databaseName=f"{tenant_key}_db",
            enabledModules=[],
            tenantDatabaseConnectionString="Server=db;Database=tenant;User Id=u;Password=p",
        )


class FakeTenantDatabase:
    def __init__(self, tenant_key: str) -> None:
        self.tenant_key = tenant_key

    def get_engine(self) -> str:
        return f"engine-{self.tenant_key}"
