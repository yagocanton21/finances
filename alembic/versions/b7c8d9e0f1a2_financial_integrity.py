"""financial integrity

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-07-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE cartoes SET limite = 0 WHERE limite IS NULL")
    op.execute("UPDATE cartoes SET saldo = 0 WHERE saldo IS NULL")
    op.execute("UPDATE cartoes SET fatura_atual = 0 WHERE fatura_atual IS NULL")
    op.execute("UPDATE cartoes SET dono = 'Eu' WHERE dono IS NULL")
    op.execute("UPDATE cartoes SET data_fatura = 15 WHERE data_fatura IS NULL")
    op.execute("UPDATE cartoes SET dia_vencimento = 20 WHERE dia_vencimento IS NULL")
    op.execute("UPDATE gasto_diarios SET pago = false WHERE pago IS NULL")
    op.execute("UPDATE gasto_diarios SET parcelas = 1 WHERE parcelas IS NULL")

    op.alter_column("cartoes", "limite", type_=sa.Numeric(12, 2), nullable=False)
    op.alter_column("cartoes", "saldo", type_=sa.Numeric(12, 2), nullable=False)
    op.alter_column(
        "cartoes", "fatura_atual", type_=sa.Numeric(12, 2), nullable=False
    )
    for coluna in ("nome", "dono", "data_fatura", "dia_vencimento"):
        op.alter_column("cartoes", coluna, nullable=False)

    op.alter_column(
        "gasto_diarios", "valor", type_=sa.Numeric(12, 2), nullable=False
    )
    for coluna in ("descricao", "data", "tipo_pagamento", "parcelas", "cartao_id"):
        op.alter_column("gasto_diarios", coluna, nullable=False)
    op.alter_column("gasto_diarios", "pago", nullable=False)
    op.add_column(
        "gasto_diarios", sa.Column("compra_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "gasto_diarios",
        sa.Column("numero_parcela", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "ix_gasto_diarios_compra_id",
        "gasto_diarios",
        ["compra_id"],
        unique=False,
    )
    op.alter_column("gasto_diarios", "numero_parcela", server_default=None)

    op.alter_column(
        "receitas", "valor", type_=sa.Numeric(12, 2), nullable=False
    )
    for coluna in ("descricao", "data", "cartao_id"):
        op.alter_column("receitas", coluna, nullable=False)


def downgrade() -> None:
    op.alter_column("receitas", "cartao_id", nullable=True)
    op.alter_column("receitas", "data", nullable=True)
    op.alter_column("receitas", "descricao", nullable=True)
    op.alter_column("receitas", "valor", type_=sa.Float(), nullable=True)

    op.drop_index("ix_gasto_diarios_compra_id", table_name="gasto_diarios")
    op.drop_column("gasto_diarios", "numero_parcela")
    op.drop_column("gasto_diarios", "compra_id")
    for coluna in ("pago", "cartao_id", "parcelas", "tipo_pagamento", "data", "descricao"):
        op.alter_column("gasto_diarios", coluna, nullable=True)
    op.alter_column("gasto_diarios", "valor", type_=sa.Float(), nullable=True)

    for coluna in ("dia_vencimento", "data_fatura", "dono", "nome"):
        op.alter_column("cartoes", coluna, nullable=True)
    op.alter_column("cartoes", "fatura_atual", type_=sa.Float(), nullable=True)
    op.alter_column("cartoes", "saldo", type_=sa.Float(), nullable=True)
    op.alter_column("cartoes", "limite", type_=sa.Float(), nullable=True)
