import json
from typing import Any

import pytest
from ape_sdk.database.migrations.checksum import calculate_sha256
from ape_sdk.database.migrations.errors import (
    MigrationChecksumMismatchError,
    MigrationLockError,
    MigrationPermissionError,
    MigrationScriptNotFoundError,
)
from ape_sdk.database.migrations.module_migration_runner import ModuleMigrationRunner
from sqlalchemy.exc import OperationalError


def test_new_migration_is_executed_and_recorded(tmp_path) -> None:  # type: ignore[no-untyped-def]
    sql_path = _write_sql(tmp_path, "001_create.sql", "CREATE TABLE example (id INT)")
    connection = FakeConnection()

    _runner(tmp_path=tmp_path, connection=connection).run()

    assert connection.executed_scripts == ["CREATE TABLE example (id INT)"]
    assert connection.history[("ecom-sync", "001_create.sql")] == calculate_sha256(sql_path)
    assert connection.commits >= 2


def test_already_run_migration_with_matching_checksum_is_skipped(tmp_path) -> None:  # type: ignore[no-untyped-def]
    sql_path = _write_sql(tmp_path, "001_create.sql", "CREATE TABLE example (id INT)")
    connection = FakeConnection()
    connection.history[("ecom-sync", "001_create.sql")] = calculate_sha256(sql_path)

    _runner(tmp_path=tmp_path, connection=connection).run()

    assert connection.executed_scripts == []


def test_already_run_migration_with_different_checksum_raises(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _write_sql(tmp_path, "001_create.sql", "CREATE TABLE example (id INT)")
    connection = FakeConnection()
    connection.history[("ecom-sync", "001_create.sql")] = "0" * 64

    with pytest.raises(MigrationChecksumMismatchError, match="checksum mismatch"):
        _runner(tmp_path=tmp_path, connection=connection).run()


def test_lock_is_released_when_migration_succeeds(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _write_sql(tmp_path, "001_create.sql", "CREATE TABLE example (id INT)")
    connection = FakeConnection()

    _runner(tmp_path=tmp_path, connection=connection).run()

    assert connection.released_locks == ["ape:ecom-sync:schema_migrations"]


def test_lock_is_released_when_migration_fails(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _write_sql(tmp_path, "001_create.sql", "CREATE TABLE example (id INT)")
    connection = FakeConnection(script_error=RuntimeError("sql failed"))

    with pytest.raises(RuntimeError, match="sql failed"):
        _runner(tmp_path=tmp_path, connection=connection).run()

    assert connection.released_locks == ["ape:ecom-sync:schema_migrations"]
    assert connection.rollbacks == 1
    assert connection.history == {}


def test_runner_refuses_to_continue_if_lock_cannot_be_acquired(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _write_sql(tmp_path, "001_create.sql", "CREATE TABLE example (id INT)")
    connection = FakeConnection(lock_result=0)

    with pytest.raises(MigrationLockError, match="Could not acquire"):
        _runner(tmp_path=tmp_path, connection=connection).run()

    assert connection.executed_scripts == []
    assert connection.released_locks == []


def test_sql_file_missing_from_migration_folder_raises_clear_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    connection = FakeConnection()

    with pytest.raises(MigrationScriptNotFoundError, match="SQL file not found"):
        _runner(tmp_path=tmp_path, connection=connection).run()

    assert connection.executed_scripts == []
    assert connection.released_locks == ["ape:ecom-sync:schema_migrations"]


def test_permission_error_creating_history_table_is_clear_and_releases_lock(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _write_sql(tmp_path, "001_create.sql", "CREATE TABLE example (id INT)")
    connection = FakeConnection(history_table_error=_mysql_error(1142))

    with pytest.raises(MigrationPermissionError, match="DDL permissions"):
        _runner(tmp_path=tmp_path, connection=connection).run()

    assert connection.released_locks == ["ape:ecom-sync:schema_migrations"]


def test_release_lock_failure_does_not_mask_original_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _write_sql(tmp_path, "001_create.sql", "CREATE TABLE example (id INT)")
    connection = FakeConnection(
        history_table_error=RuntimeError("history failed"),
        release_error=RuntimeError("release failed"),
    )

    with pytest.raises(RuntimeError, match="history failed"):
        _runner(tmp_path=tmp_path, connection=connection).run()


def _runner(*, tmp_path, connection: "FakeConnection") -> ModuleMigrationRunner:  # type: ignore[no-untyped-def]
    return ModuleMigrationRunner(
        database_connection=connection,  # type: ignore[arg-type]
        module_name="ecom-sync",
        manifest_json=json.dumps(
            {
                "moduleName": "ecom-sync",
                "schemaVersion": 1,
                "migrations": [{"name": "001_create.sql"}],
            }
        ),
        sql_files_path=tmp_path,
    )


def _write_sql(tmp_path, name: str, content: str):  # type: ignore[no-untyped-def]
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


class FakeResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one(self) -> Any:
        return self.value

    def scalar_one_or_none(self) -> Any:
        return self.value


class FakeConnection:
    def __init__(
        self,
        *,
        lock_result: int = 1,
        script_error: Exception | None = None,
        history_table_error: Exception | None = None,
        release_error: Exception | None = None,
    ) -> None:
        self.lock_result = lock_result
        self.script_error = script_error
        self.history_table_error = history_table_error
        self.release_error = release_error
        self.history: dict[tuple[str, str], str] = {}
        self.executed_scripts: list[str] = []
        self.released_locks: list[str] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, statement, parameters: dict[str, Any] | None = None) -> FakeResult:  # type: ignore[no-untyped-def]
        sql = str(statement)
        values = parameters or {}
        if "GET_LOCK" in sql:
            return FakeResult(self.lock_result)
        if "RELEASE_LOCK" in sql:
            if self.release_error is not None:
                raise self.release_error
            self.released_locks.append(values["lock_name"])
            return FakeResult(1)
        if "CREATE TABLE IF NOT EXISTS module_schema_migrations" in sql:
            if self.history_table_error is not None:
                raise self.history_table_error
            return FakeResult(None)
        if "SELECT script_checksum" in sql:
            return FakeResult(
                self.history.get((values["module_name"], values["script_name"]))
            )
        if "INSERT INTO module_schema_migrations" in sql:
            self.history[(values["module_name"], values["script_name"])] = values[
                "script_checksum"
            ]
            return FakeResult(None)
        raise AssertionError(f"Unexpected SQL: {sql}")

    def exec_driver_sql(self, sql: str) -> None:
        if self.script_error is not None:
            raise self.script_error
        self.executed_scripts.append(sql)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _mysql_error(error_code: int) -> OperationalError:
    class OriginalError:
        args = (error_code, "permission denied")

    return OperationalError("SELECT 1", {}, OriginalError())
