class MigrationError(Exception):
    """Base error raised by the module migration runner."""


class MigrationManifestError(MigrationError):
    """Raised when a migration manifest is invalid."""


class MigrationChecksumMismatchError(MigrationError):
    """Raised when an already-run migration script has been edited."""


class MigrationLockError(MigrationError):
    """Raised when a tenant database migration lock cannot be acquired."""


class MigrationScriptNotFoundError(MigrationError):
    """Raised when a manifest entry points at a missing SQL file."""


class MigrationPermissionError(MigrationError):
    """Raised when the database user cannot perform migration DDL."""
