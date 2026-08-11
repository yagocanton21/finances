"""add payment origin and balance movement flag"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pagamentos_fatura",
        sa.Column("origem", sa.String(20), nullable=False, server_default="sistema"),
    )
    op.add_column(
        "pagamentos_fatura",
        sa.Column("movimentou_saldo", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("pagamentos_fatura", "origem", server_default=None)
    op.alter_column("pagamentos_fatura", "movimentou_saldo", server_default=None)


def downgrade() -> None:
    op.drop_column("pagamentos_fatura", "movimentou_saldo")
    op.drop_column("pagamentos_fatura", "origem")
