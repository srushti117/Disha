"""Database layer.

PostgreSQL/PostGIS in production (real Geometry columns + GiST indexes via GeoAlchemy2).
SQLite fallback stores geometries as GeoJSON text so the platform runs with zero setup.
Application code always sees GeoJSON-like dicts.
"""
import json
from typing import Any, Iterator

from shapely.geometry import mapping, shape
from sqlalchemy import Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import get_settings

settings = get_settings()
IS_POSTGIS = settings.database_url.startswith("postgresql")


if IS_POSTGIS:
    from geoalchemy2 import Geometry as _Geometry
    from geoalchemy2.shape import to_shape as _to_shape

    class Geom(_Geometry):
        """PostGIS geometry(…, 4326) with GiST index. Python value: GeoJSON dict."""

        cache_ok = True

        def __init__(self, geom_type: str = "GEOMETRY"):
            super().__init__(geometry_type=geom_type, srid=4326, spatial_index=True)

        def bind_processor(self, dialect):
            inner = super().bind_processor(dialect)

            def process(value: Any):
                if value is None:
                    return None
                geom = shape(value) if isinstance(value, dict) else value
                ewkt = f"SRID=4326;{geom.wkt}"
                return inner(ewkt) if inner else ewkt

            return process

        def result_processor(self, dialect, coltype):
            inner = super().result_processor(dialect, coltype)

            def process(value: Any):
                if value is None:
                    return None
                elem = inner(value) if inner else value
                return mapping(_to_shape(elem))

            return process

else:

    class Geom(TypeDecorator):  # type: ignore[no-redef]
        """SQLite fallback: GeoJSON text. Python value: GeoJSON dict."""

        impl = Text
        cache_ok = True

        def __init__(self, geom_type: str = "GEOMETRY"):
            super().__init__()
            self.geom_type = geom_type

        def process_bind_param(self, value: Any, dialect):
            if value is None:
                return None
            geom = shape(value) if isinstance(value, dict) else value
            return json.dumps(mapping(geom))

        def process_result_value(self, value: Any, dialect):
            return None if value is None else json.loads(value)


class Base(DeclarativeBase):
    pass


_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args, pool_pre_ping=True)

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    if IS_POSTGIS:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS postgis")
    from .. import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine)
