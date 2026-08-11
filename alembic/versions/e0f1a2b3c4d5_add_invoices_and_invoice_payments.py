"""add invoices and invoice payments"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e0f1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "faturas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cartao_id", sa.Integer(), nullable=False),
        sa.Column("mes_ref", sa.Integer(), nullable=False),
        sa.Column("ano_ref", sa.Integer(), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("situacao", sa.String(20), nullable=False, server_default="aberta"),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["cartao_id"], ["cartoes.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "cartao_id", "mes_ref", "ano_ref", name="uq_faturas_cartao_competencia"
        ),
    )
    op.create_index("ix_faturas_id", "faturas", ["id"], unique=False)
    op.create_index("ix_faturas_cartao_id", "faturas", ["cartao_id"], unique=False)

    op.create_table(
        "pagamentos_fatura",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fatura_id", sa.Integer(), nullable=False),
        sa.Column("cartao_id", sa.Integer(), nullable=False),
        sa.Column("mes_ref", sa.Integer(), nullable=False),
        sa.Column("ano_ref", sa.Integer(), nullable=False),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.Column("data_pagamento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("situacao", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=True),
        sa.ForeignKeyConstraint(["fatura_id"], ["faturas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cartao_id"], ["cartoes.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("idempotency_key", name="uq_pagamentos_fatura_idempotency_key"),
    )
    op.create_index("ix_pagamentos_fatura_id", "pagamentos_fatura", ["id"], unique=False)
    op.create_index(
        "ix_pagamentos_fatura_fatura_id", "pagamentos_fatura", ["fatura_id"], unique=False
    )
    op.create_index(
        "ix_pagamentos_fatura_cartao_id", "pagamentos_fatura", ["cartao_id"], unique=False
    )
    op.create_index(
        "ix_pagamentos_fatura_idempotency_key",
        "pagamentos_fatura",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_pagamentos_fatura_idempotency_key", table_name="pagamentos_fatura")
    op.drop_index("ix_pagamentos_fatura_cartao_id", table_name="pagamentos_fatura")
    op.drop_index("ix_pagamentos_fatura_fatura_id", table_name="pagamentos_fatura")
    op.drop_index("ix_pagamentos_fatura_id", table_name="pagamentos_fatura")
    op.drop_table("pagamentos_fatura")
    op.drop_index("ix_faturas_cartao_id", table_name="faturas")
    op.drop_index("ix_faturas_id", table_name="faturas")
    op.drop_table("faturas")
