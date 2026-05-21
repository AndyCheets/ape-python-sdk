from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ape_sdk.database.migrations.errors import MigrationLockError

logger = logging.getLogger(__name__)


class MySqlMigrationLock:
    def __init__(
        self,
        connection: Connection,
        *,
        module_name: str,
        timeout_seconds: int = 30,
    ) -> None:
        self.connection = connection
        self.module_name = module_name
        self.timeout_seconds = timeout_seconds
        self.lock_name = f"ape:{module_name}:schema_migrations"
        self.acquired = False

    def acquire(self) -> None:
        result = self.connection.execute(
            text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
            {
                "lock_name": self.lock_name,
                "timeout_seconds": self.timeout_seconds,
            },
        ).scalar_one()
        if result != 1:
            raise MigrationLockError(
                f"Could not acquire migration lock for module {self.module_name}"
            )
        self.acquired = True
        logger.info(
            "Acquired module migration lock module_name=%s lock_name=%s",
            self.module_name,
            self.lock_name,
        )

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            self.connection.execute(
                text("SELECT RELEASE_LOCK(:lock_name)"),
                {"lock_name": self.lock_name},
            )
            logger.info(
                "Released module migration lock module_name=%s lock_name=%s",
                self.module_name,
                self.lock_name,
            )
        except Exception:
            logger.exception(
                "Failed to release module migration lock module_name=%s lock_name=%s",
                self.module_name,
                self.lock_name,
            )
        finally:
            self.acquired = False

    def __enter__(self) -> MySqlMigrationLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:  # type: ignore[no-untyped-def]
        self.release()
