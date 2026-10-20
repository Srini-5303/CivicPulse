"""langgraph checkpoints

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op
from langgraph.checkpoint.postgres import PostgresSaver

from libs.common.config import settings
from libs.common.db import psycopg_url

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKPOINT_TABLES = (
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
)


def upgrade() -> None:
    # setup() runs CREATE INDEX CONCURRENTLY, which waits for every open transaction, so
    # Alembic's own must be closed first or the migration hangs. Bumping
    # langgraph-checkpoint-postgres may add checkpoint migrations; add a new revision that
    # calls setup() again when it does.
    with op.get_context().autocommit_block():
        with PostgresSaver.from_conn_string(psycopg_url(settings.migration_database_url)) as saver:
            saver.setup()
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(CHECKPOINT_TABLES)} TO app")


def downgrade() -> None:
    for table in CHECKPOINT_TABLES:
        op.execute(f"DROP TABLE {table}")
