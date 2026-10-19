import pytest
from sqlalchemy import make_url, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine

from libs.common.config import settings


async def test_app_role_cannot_modify_audit_log() -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        await conn.execute(text("INSERT INTO audit_log (actor, action) VALUES ('test', 'probe')"))
        with pytest.raises(ProgrammingError, match="permission denied"):
            await conn.execute(text("UPDATE audit_log SET action = 'tampered'"))
        await conn.rollback()
    await engine.dispose()


async def test_history_role_reads_public_view_only() -> None:
    url = make_url(settings.database_url).set(
        username="history_ro", password=settings.history_ro_password
    )
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT count(*) FROM v_complaints_public"))
        with pytest.raises(ProgrammingError, match="permission denied"):
            await conn.execute(text("SELECT text_scrubbed FROM complaints"))
    await engine.dispose()
