from collections.abc import Callable
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from ape_sdk.tenant.context import TenantWorkerContext


SessionFactory = Callable[[], Session]


class TenantDatabase:
    """Lazy tenant database access for workers that need tenant reads or writes."""

    def __init__(
        self,
        tenant_context: TenantWorkerContext,
        session_factory_builder: Callable[[str], sessionmaker[Session]] | None = None,
    ) -> None:
        self.tenant_context = tenant_context
        self.session_factory_builder = session_factory_builder or create_tenant_session_factory
        self._session_factory: sessionmaker[Session] | None = None

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self.get_session_factory()() as session:
            yield session

    def verify_connection(self) -> None:
        with self.session() as session:
            session.execute(text("SELECT 1"))

    def get_session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            self._session_factory = self.session_factory_builder(
                self.tenant_context.tenant_database_connection_string
            )
        return self._session_factory


def create_tenant_session_factory(connection_string: str) -> sessionmaker[Session]:
    engine = create_engine(
        _sqlalchemy_url_from_connection_string(connection_string),
        pool_pre_ping=True,
    )
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _sqlalchemy_url_from_connection_string(connection_string: str) -> URL:
    values = _parse_connection_string(connection_string)
    return URL.create(
        "mysql+pymysql",
        username=values.get("user id") or values.get("uid") or values.get("user"),
        password=values.get("password") or values.get("pwd"),
        host=values.get("server") or values.get("host"),
        port=_optional_int(values.get("port")),
        database=values.get("database"),
    )


def _parse_connection_string(connection_string: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in connection_string.split(";"):
        key, separator, value = part.partition("=")
        if separator:
            values[key.strip().lower()] = value.strip()
    return values


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None
