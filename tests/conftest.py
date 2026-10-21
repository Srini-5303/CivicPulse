import os
import subprocess
import sys

import psycopg
import pytest
from sqlalchemy import make_url

from libs.common.config import settings

TEST_DB = "civicpulse_test"

# Repoint settings before anything imports libs.common.db, which builds its engine from them at
# import; conftest is always imported first, so the dev database is never touched.
assert "libs.common.db" not in sys.modules, "engine already bound to the dev database"
for _field in ("database_url", "migration_database_url"):
    _url = make_url(getattr(settings, _field)).set(database=TEST_DB)
    setattr(settings, _field, _url.render_as_string(hide_password=False))


@pytest.fixture(scope="session", autouse=True)
def test_database() -> None:
    """Recreate the test database from migrations, so every run starts empty."""
    admin_url = make_url(settings.migration_database_url).set(
        drivername="postgresql", database="postgres"
    )
    with psycopg.connect(admin_url.render_as_string(hide_password=False), autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {TEST_DB}")
    env = os.environ | {
        "DATABASE_URL": settings.database_url,
        "MIGRATION_DATABASE_URL": settings.migration_database_url,
    }
    subprocess.run(["alembic", "upgrade", "head"], env=env, check=True, capture_output=True)
