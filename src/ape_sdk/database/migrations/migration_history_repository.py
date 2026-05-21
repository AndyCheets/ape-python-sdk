from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection


class MigrationHistoryRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def ensure_history_table(self) -> None:
        self.connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS module_schema_migrations (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    module_name VARCHAR(100) NOT NULL,
                    script_name VARCHAR(255) NOT NULL,
                    script_checksum CHAR(64) NOT NULL,
                    executed_at_utc DATETIME NOT NULL,
                    execution_time_ms INT NULL,
                    UNIQUE KEY ux_module_schema_migrations_module_script (
                        module_name,
                        script_name
                    )
                )
                """
            )
        )

    def get_script_checksum(self, *, module_name: str, script_name: str) -> str | None:
        result = self.connection.execute(
            text(
                """
                SELECT script_checksum
                FROM module_schema_migrations
                WHERE module_name = :module_name
                  AND script_name = :script_name
                """
            ),
            {
                "module_name": module_name,
                "script_name": script_name,
            },
        )
        return result.scalar_one_or_none()

    def record_success(
        self,
        *,
        module_name: str,
        script_name: str,
        script_checksum: str,
        execution_time_ms: int | None,
    ) -> None:
        self.connection.execute(
            text(
                """
                INSERT INTO module_schema_migrations (
                    module_name,
                    script_name,
                    script_checksum,
                    executed_at_utc,
                    execution_time_ms
                )
                VALUES (
                    :module_name,
                    :script_name,
                    :script_checksum,
                    :executed_at_utc,
                    :execution_time_ms
                )
                """
            ),
            {
                "module_name": module_name,
                "script_name": script_name,
                "script_checksum": script_checksum,
                "executed_at_utc": datetime.now(UTC).replace(tzinfo=None),
                "execution_time_ms": execution_time_ms,
            },
        )
