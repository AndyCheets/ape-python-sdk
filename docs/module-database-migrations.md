# Module Database Migrations

APE modules own their tenant database tables. The SDK migration runner applies module-owned SQL
files to tenant database connections only; it does not connect to or modify the APE control
database.

Run a module's migrations for one tenant database connection:

```python
from ape_sdk.database.migrations import ModuleMigrationRunner

runner = ModuleMigrationRunner(
    database_connection=tenant_engine,
    module_name="ecom-sync",
    manifest_path="src/ape_ecom_sync/db/migrations/migration-manifest.json",
    sql_files_path="src/ape_ecom_sync/db/migrations",
)

runner.run()
```

Run a module's migrations for every active tenant at service startup:

```python
from ape_sdk.control.client import ControlApiClient
from ape_sdk.database.migrations import TenantModuleMigrationRunner

control_api_client = ControlApiClient(
    base_url=settings.control_api.base_url,
    token=settings.control_api.token,
)

TenantModuleMigrationRunner(
    control_api_client=control_api_client,
    module_name="ecom-sync",
    manifest_path="src/ape_ecom_sync/db/migrations/migration-manifest.json",
    sql_files_path="src/ape_ecom_sync/db/migrations",
).run_for_active_tenants()
```

Manifest format:

```json
{
  "moduleName": "ecom-sync",
  "schemaVersion": 1,
  "migrations": [
    {
      "name": "001_create_ecom_sync_configs.sql",
      "description": "Create ecommerce sync configuration table"
    }
  ]
}
```

The runner:

- creates `module_schema_migrations` in the tenant database if needed
- acquires `GET_LOCK('ape:{module_name}:schema_migrations', timeout_seconds)`
- calculates a SHA-256 checksum for each SQL file
- executes only pending scripts
- records successful scripts after execution
- fails if an already-recorded script checksum changes
- releases the MySQL advisory lock in a `finally` block

SQL files are passed to SQLAlchemy `Connection.exec_driver_sql()` exactly as stored. Keep each
migration file compatible with the tenant database driver configuration. If a driver is not
configured for multiple statements, use one executable SQL statement per file.

Migrations require a tenant database connection with DDL permissions such as `CREATE`, `ALTER`,
`INDEX`, and `REFERENCES`.
