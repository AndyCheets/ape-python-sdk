from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ape_sdk.database.migrations.checksum import calculate_sha256
from ape_sdk.database.migrations.errors import (
    MigrationChecksumMismatchError,
    MigrationPermissionError,
    MigrationScriptNotFoundError,
)
from ape_sdk.database.migrations.migration_history_repository import (
    MigrationHistoryRepository,
)
from ape_sdk.database.migrations.migration_lock import MySqlMigrationLock
from ape_sdk.database.migrations.migration_manifest import MigrationManifest

logger = logging.getLogger(__name__)


class ModuleMigrationRunner:
    def __init__(
        self,
        *,
        database_connection: Engine | Connection | Session,
        module_name: str,
        sql_files_path: str | Path,
        manifest_json: str | None = None,
        manifest_path: str | Path | None = None,
        lock_timeout_seconds: int = 30,
    ) -> None:
        if not manifest_json and not manifest_path:
            raise ValueError("Either manifest_json or manifest_path is required")
        if manifest_json and manifest_path:
            raise ValueError("Provide manifest_json or manifest_path, not both")

        self.database_connection = database_connection
        self.module_name = module_name
        self.sql_files_path = Path(sql_files_path)
        self.manifest_json = manifest_json
        self.manifest_path = Path(manifest_path) if manifest_path else None
        self.lock_timeout_seconds = lock_timeout_seconds

    def run(self) -> None:
        manifest = self._load_manifest()
        logger.info(
            "Starting module database migrations module_name=%s migration_count=%s",
            self.module_name,
            len(manifest.migrations),
        )

        with self._connect() as connection:
            lock = MySqlMigrationLock(
                connection,
                module_name=self.module_name,
                timeout_seconds=self.lock_timeout_seconds,
            )
            try:
                lock.acquire()
                history_repository = MigrationHistoryRepository(connection)
                self._ensure_history_table(history_repository)
                self._commit(connection)

                for migration in manifest.migrations:
                    self._run_migration(
                        connection=connection,
                        history_repository=history_repository,
                        script_name=migration.name,
                    )
            except BaseException:
                self._try_rollback(connection)
                raise
            finally:
                lock.release()

        logger.info("Completed module database migrations module_name=%s", self.module_name)

    def _ensure_history_table(self, history_repository: MigrationHistoryRepository) -> None:
        try:
            history_repository.ensure_history_table()
        except OperationalError as exc:
            if _is_mysql_permission_denied(exc):
                raise MigrationPermissionError(
                    "Database user does not have permission to create the "
                    "module_schema_migrations table. Module migrations require a tenant database "
                    "connection with DDL permissions such as CREATE, ALTER, INDEX and REFERENCES."
                ) from exc
            raise

    def _run_migration(
        self,
        *,
        connection: Connection,
        history_repository: MigrationHistoryRepository,
        script_name: str,
    ) -> None:
        script_path = self.sql_files_path / script_name
        if not script_path.is_file():
            raise MigrationScriptNotFoundError(
                f"Migration SQL file not found module_name={self.module_name} "
                f"script_name={script_name}"
            )

        checksum = calculate_sha256(script_path)
        previous_checksum = history_repository.get_script_checksum(
            module_name=self.module_name,
            script_name=script_name,
        )

        if previous_checksum is None:
            self._execute_and_record_migration(
                connection=connection,
                history_repository=history_repository,
                script_name=script_name,
                script_path=script_path,
                checksum=checksum,
            )
            return

        if previous_checksum == checksum:
            logger.info(
                "Skipping already-applied module migration module_name=%s script_name=%s",
                self.module_name,
                script_name,
            )
            return

        raise MigrationChecksumMismatchError(
            f"Migration checksum mismatch module_name={self.module_name} "
            f"script_name={script_name}"
        )

    def _execute_and_record_migration(
        self,
        *,
        connection: Connection,
        history_repository: MigrationHistoryRepository,
        script_name: str,
        script_path: Path,
        checksum: str,
    ) -> None:
        logger.info(
            "Executing module migration module_name=%s script_name=%s",
            self.module_name,
            script_name,
        )
        sql = script_path.read_text(encoding="utf-8")
        started = perf_counter()
        try:
            connection.exec_driver_sql(sql)
        except OperationalError as exc:
            if _is_mysql_permission_denied(exc):
                raise MigrationPermissionError(
                    "Database user does not have permission to execute module migration SQL "
                    f"module_name={self.module_name} script_name={script_name}. Module migrations "
                    "require a tenant database connection with DDL permissions such as CREATE, "
                    "ALTER, INDEX and REFERENCES."
                ) from exc
            raise
        execution_time_ms = int((perf_counter() - started) * 1000)
        history_repository.record_success(
            module_name=self.module_name,
            script_name=script_name,
            script_checksum=checksum,
            execution_time_ms=execution_time_ms,
        )
        self._commit(connection)
        logger.info(
            "Recorded module migration module_name=%s script_name=%s execution_time_ms=%s",
            self.module_name,
            script_name,
            execution_time_ms,
        )

    def _load_manifest(self) -> MigrationManifest:
        if self.manifest_json is not None:
            return MigrationManifest.from_json_content(
                self.manifest_json,
                expected_module_name=self.module_name,
            )
        if self.manifest_path is None:
            raise ValueError("manifest_path is required when manifest_json is not provided")
        return MigrationManifest.from_path(
            self.manifest_path,
            expected_module_name=self.module_name,
        )

    @contextmanager
    def _connect(self) -> Iterator[Connection]:
        if isinstance(self.database_connection, Engine):
            with self.database_connection.connect() as connection:
                yield connection
            return
        if isinstance(self.database_connection, Session):
            yield self.database_connection.connection()
            return
        yield self.database_connection

    def _commit(self, connection: Connection) -> None:
        if isinstance(self.database_connection, Session):
            self.database_connection.commit()
            return
        connection.commit()

    def _rollback(self, connection: Connection) -> None:
        if isinstance(self.database_connection, Session):
            self.database_connection.rollback()
            return
        connection.rollback()

    def _try_rollback(self, connection: Connection) -> None:
        try:
            self._rollback(connection)
        except Exception:
            logger.exception(
                "Failed to rollback module migration transaction module_name=%s",
                self.module_name,
            )


def _is_mysql_permission_denied(exc: OperationalError) -> bool:
    original_error = getattr(exc, "orig", None)
    error_code = None
    if hasattr(original_error, "args") and original_error.args:
        error_code = original_error.args[0]
    return error_code in {1044, 1045, 1142}
