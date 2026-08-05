"""Compatibility bridge for databases created from the legacy migration chain.

Revision ID bfd8a3e54c8f is present in existing installations but its migration
file is not part of this repository anymore. Those databases already contain
the schema produced through the financial-integrity migration, so this bridge
intentionally performs no schema changes and lets Alembic continue safely.
"""

from typing import Sequence, Union


revision: str = "bfd8a3e54c8f"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
