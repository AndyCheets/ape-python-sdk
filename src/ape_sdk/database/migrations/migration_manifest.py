from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ape_sdk.database.migrations.errors import MigrationManifestError


@dataclass(frozen=True)
class MigrationManifestEntry:
    name: str
    description: str | None = None


@dataclass(frozen=True)
class MigrationManifest:
    module_name: str
    schema_version: int
    migrations: tuple[MigrationManifestEntry, ...]

    @classmethod
    def from_json_content(
        cls,
        content: str,
        *,
        expected_module_name: str,
    ) -> MigrationManifest:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise MigrationManifestError("Migration manifest must be valid JSON") from exc
        return cls.from_dict(payload, expected_module_name=expected_module_name)

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        expected_module_name: str,
    ) -> MigrationManifest:
        manifest_path = Path(path)
        return cls.from_json_content(
            manifest_path.read_text(encoding="utf-8"),
            expected_module_name=expected_module_name,
        )

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        *,
        expected_module_name: str,
    ) -> MigrationManifest:
        if not isinstance(payload, dict):
            raise MigrationManifestError("Migration manifest must be a JSON object")

        module_name = _required_text(payload, "moduleName")
        if module_name != expected_module_name:
            raise MigrationManifestError(
                "Migration manifest moduleName does not match runner module_name"
            )

        raw_migrations = payload.get("migrations")
        if not isinstance(raw_migrations, list):
            raise MigrationManifestError("Migration manifest migrations must be a list")

        migrations = tuple(_parse_entry(entry) for entry in raw_migrations)
        return cls(
            module_name=module_name,
            schema_version=int(payload.get("schemaVersion") or 1),
            migrations=migrations,
        )


def _parse_entry(value: Any) -> MigrationManifestEntry:
    if not isinstance(value, dict):
        raise MigrationManifestError("Migration manifest migration entries must be objects")
    name = _required_text(value, "name")
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise MigrationManifestError("Migration script name must be relative to the SQL folder")
    description = value.get("description")
    if description is not None and not isinstance(description, str):
        raise MigrationManifestError("Migration description must be text when provided")
    return MigrationManifestEntry(name=name, description=description)


def _required_text(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise MigrationManifestError(f"Migration manifest {field_name} is required")
    return value.strip()
