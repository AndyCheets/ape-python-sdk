import json

import pytest
from ape_sdk.database.migrations.errors import MigrationManifestError
from ape_sdk.database.migrations.migration_manifest import MigrationManifest


def test_manifest_parses_valid_json() -> None:
    manifest = MigrationManifest.from_json_content(
        json.dumps(
            {
                "moduleName": "ecom-sync",
                "schemaVersion": 1,
                "migrations": [
                    {
                        "name": "001_create_configs.sql",
                        "description": "Create configs",
                    }
                ],
            }
        ),
        expected_module_name="ecom-sync",
    )

    assert manifest.module_name == "ecom-sync"
    assert manifest.schema_version == 1
    assert manifest.migrations[0].name == "001_create_configs.sql"
    assert manifest.migrations[0].description == "Create configs"


def test_manifest_validation_fails_when_module_name_is_missing() -> None:
    with pytest.raises(MigrationManifestError, match="moduleName"):
        MigrationManifest.from_json_content(
            json.dumps({"schemaVersion": 1, "migrations": []}),
            expected_module_name="ecom-sync",
        )


def test_manifest_validation_fails_when_migrations_is_missing() -> None:
    with pytest.raises(MigrationManifestError, match="migrations"):
        MigrationManifest.from_json_content(
            json.dumps({"moduleName": "ecom-sync", "schemaVersion": 1}),
            expected_module_name="ecom-sync",
        )


def test_manifest_validation_fails_when_migration_entry_has_no_name() -> None:
    with pytest.raises(MigrationManifestError, match="name"):
        MigrationManifest.from_json_content(
            json.dumps(
                {
                    "moduleName": "ecom-sync",
                    "schemaVersion": 1,
                    "migrations": [{"description": "No name"}],
                }
            ),
            expected_module_name="ecom-sync",
        )


def test_manifest_validation_fails_when_module_name_differs() -> None:
    with pytest.raises(MigrationManifestError, match="moduleName"):
        MigrationManifest.from_json_content(
            json.dumps({"moduleName": "other", "schemaVersion": 1, "migrations": []}),
            expected_module_name="ecom-sync",
        )
