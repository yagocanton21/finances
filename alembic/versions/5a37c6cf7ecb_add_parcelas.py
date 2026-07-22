"""add_parcelas

Revision ID: 5a37c6cf7ecb
Revises: ff393dd68372
Create Date: 2026-07-22 11:08:13.714968

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a37c6cf7ecb'
down_revision: Union[str, Sequence[str], None] = 'ff393dd68372'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('gasto_diarios', sa.Column('parcelas', sa.Integer(), nullable=True))
    op.execute("UPDATE gasto_diarios SET parcelas = 1")

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('gasto_diarios', 'parcelas')
    # ### end Alembic commands ###
