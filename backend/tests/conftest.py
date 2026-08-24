import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# La configuración se lee al importar la app: fijar el entorno de pruebas antes.
os.environ["USAGE_TRACKER_ENABLED"] = "false"
# >= 32 bytes: mínimo recomendado para HMAC-SHA256 (RFC 7518 §3.2); evita
# el InsecureKeyLengthWarning de pyjwt.
os.environ["SECRET_KEY"] = "clave-secreta-solo-para-pruebas!"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
# Sin secreto por defecto en tests (un .env local podría definirlo y filtrar
# configuración de producción al hook interno de MediaMTX).
os.environ["MEDIAMTX_AUTH_SECRET"] = ""
# El bootstrap de super-admin se configura test a test (monkeypatch): se parte de
# la configuración apagada para no depender de un .env local.
os.environ["SUPERADMIN_EMAILS"] = ""
os.environ["SUPERADMIN_BOOTSTRAP_TOKEN"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Plan

PLAN_ROWS = [
    {
        "code": "free",
        "name": "Gratis",
        "price_usd_month": Decimal("0.00"),
        "max_devices": 1,
        "max_resolution": "720p",
        "max_fps": 30,
        "monthly_hours": 15,
        "max_recording_gb": 1,
        "features": ["1 dispositivo", "720p a 30 fps", "15 horas por mes"],
        "sort_order": 1,
    },
    {
        "code": "creator",
        "name": "Creador",
        "price_usd_month": Decimal("4.99"),
        "max_devices": 1,
        "max_resolution": "1080p",
        "max_fps": 30,
        "monthly_hours": 60,
        "max_recording_gb": 5,
        "features": ["1 dispositivo", "1080p a 30 fps", "60 horas por mes"],
        "sort_order": 2,
    },
    {
        "code": "pro",
        "name": "Pro",
        "price_usd_month": Decimal("9.99"),
        "max_devices": 2,
        "max_resolution": "1080p",
        "max_fps": 60,
        "monthly_hours": 150,
        "max_recording_gb": 20,
        "features": ["2 dispositivos", "1080p a 60 fps", "150 horas por mes"],
        "sort_order": 3,
    },
    {
        "code": "studio",
        "name": "Estudio",
        "price_usd_month": Decimal("19.99"),
        "max_devices": 4,
        "max_resolution": "1080p",
        "max_fps": 60,
        "monthly_hours": None,
        "max_recording_gb": 40,
        "features": ["4 dispositivos", "1080p a 60 fps", "Horas ilimitadas (uso justo)"],
        "sort_order": 4,
    },
]


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite ignora las claves foráneas salvo que se pidan explícitamente en cada
    # conexión. Sin esto los ON DELETE CASCADE / SET NULL no se ejercitan y un error
    # en las cascadas pasaría inadvertido en los tests.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        for row in PLAN_ROWS:
            session.add(Plan(**row))
        session.commit()
    yield factory
    engine.dispose()


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
