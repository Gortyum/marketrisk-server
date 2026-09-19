"""Configura una base SQLite temporal aislada por test."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP_DIR = Path(tempfile.mkdtemp(prefix="market_risk_tests_"))
os.environ["COURSE_DATABASE_URL"] = f"sqlite:///{_TMP_DIR / 'unused.db'}"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def db_session():
    """Base SQLite en un archivo temporal nuevo por cada test."""
    db_path = Path(tempfile.mkdtemp(prefix="mrt_")) / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def sample_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "sample"