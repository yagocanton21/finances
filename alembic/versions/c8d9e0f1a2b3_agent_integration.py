"""agent integration and audit

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-08-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conexao = op.get_bind()
    inspetor = sa.inspect(conexao)
    colunas_cartoes = {c["name"] for c in inspetor.get_columns("cartoes")}

    # Instalacoes antigas receberam esta coluna antes de ela virar migration.
    if "ativo" not in colunas_cartoes:
        op.add_column(
            "cartoes",
            sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        )

    for tabela in ("gasto_diarios", "receitas"):
        op.add_column(
            tabela,
            sa.Column("origem", sa.String(30), nullable=False, server_default="frontend"),
        )
        op.add_column(tabela, sa.Column("external_id", sa.String(120), nullable=True))
        op.create_index(f"ix_{tabela}_origem", tabela, ["origem"])
        op.create_index(f"ix_{tabela}_external_id", tabela, ["external_id"])
        op.alter_column(tabela, "origem", server_default=None)

    op.create_table(
        "auditoria_agente",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(120), nullable=False),
        sa.Column("agente", sa.String(80), nullable=False, server_default="hermes"),
        sa.Column("acao", sa.String(40), nullable=False),
        sa.Column("entidade", sa.String(40), nullable=False),
        sa.Column("entidade_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("requisicao", sa.JSON(), nullable=False),
        sa.Column("resposta", sa.JSON(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("external_id", name="uq_auditoria_agente_external_id"),
    )
    op.create_index(
        "ix_auditoria_agente_external_id",
        "auditoria_agente",
        ["external_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_auditoria_agente_external_id", table_name="auditoria_agente")
    op.drop_table("auditoria_agente")
    for tabela in ("receitas", "gasto_diarios"):
        op.drop_index(f"ix_{tabela}_external_id", table_name=tabela)
        op.drop_index(f"ix_{tabela}_origem", table_name=tabela)
        op.drop_column(tabela, "external_id")
        op.drop_column(tabela, "origem")
