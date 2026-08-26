"""evolve accounts, invoices, purchases and planning

Revision ID: a2b3c4d5e6f7
Revises: c4d5e6f7a8b9
Create Date: 2026-08-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE categorias SET nome = 'Sem categoria ' || id WHERE nome IS NULL OR btrim(nome) = ''")
    op.execute(
        """
        WITH duplicadas AS (
            SELECT id, MIN(id) OVER (PARTITION BY lower(btrim(nome))) AS manter
            FROM categorias
        )
        UPDATE gasto_diarios g
        SET categoria_id = d.manter
        FROM duplicadas d
        WHERE g.categoria_id = d.id AND d.id <> d.manter
        """
    )
    op.execute(
        """
        WITH duplicadas AS (
            SELECT id, MIN(id) OVER (PARTITION BY lower(btrim(nome))) AS manter
            FROM categorias
        )
        UPDATE receitas r
        SET categoria_id = d.manter
        FROM duplicadas d
        WHERE r.categoria_id = d.id AND d.id <> d.manter
        """
    )
    op.execute(
        """
        DELETE FROM categorias c
        USING categorias anterior
        WHERE lower(btrim(c.nome)) = lower(btrim(anterior.nome))
          AND c.id > anterior.id
        """
    )
    op.alter_column("categorias", "nome", existing_type=sa.String(), nullable=False)
    op.create_index("uq_categorias_nome_normalizado", "categorias", [sa.text("lower(btrim(nome))")], unique=True)

    op.create_table(
        "contas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("dono", sa.String(80), nullable=False, server_default="Eu"),
        sa.Column("tipo", sa.String(20), nullable=False, server_default="corrente"),
        sa.Column("saldo", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_contas_id", "contas", ["id"])
    op.execute(
        """
        INSERT INTO contas (id, nome, dono, saldo)
        SELECT id, nome, dono, saldo FROM cartoes
        """
    )
    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('contas', 'id'),
            GREATEST(COALESCE((SELECT MAX(id) FROM contas), 1), 1),
            EXISTS (SELECT 1 FROM contas)
        )
        """
    )

    op.add_column("cartoes", sa.Column("limite_total", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("cartoes", sa.Column("conta_padrao_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_cartoes_conta_padrao", "cartoes", "contas", ["conta_padrao_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index("ix_cartoes_conta_padrao_id", "cartoes", ["conta_padrao_id"])
    op.execute("UPDATE cartoes SET conta_padrao_id = id")
    op.execute(
        """
        UPDATE cartoes c
        SET limite_total = c.limite + COALESCE((
            SELECT SUM(g.valor)
            FROM gasto_diarios g
            WHERE g.cartao_id = c.id
              AND g.tipo_pagamento = 'credito'
              AND g.pago IS FALSE
        ), 0)
        """
    )

    op.create_table(
        "compras",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("descricao", sa.String(255), nullable=False),
        sa.Column("valor_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("valor_reembolsado", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("data_compra", sa.DateTime(), nullable=False),
        sa.Column("parcelas", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tipo_pagamento", sa.String(20), nullable=False),
        sa.Column("cartao_id", sa.Integer(), nullable=True),
        sa.Column("conta_id", sa.Integer(), nullable=True),
        sa.Column("categoria_id", sa.Integer(), nullable=True),
        sa.Column("situacao", sa.String(20), nullable=False, server_default="ativa"),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cartao_id"], ["cartoes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["conta_id"], ["contas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_compras_data_compra", "compras", ["data_compra"])
    op.create_index("ix_compras_cartao_id", "compras", ["cartao_id"])
    op.create_index("ix_compras_conta_id", "compras", ["conta_id"])
    op.execute(
        """
        INSERT INTO compras (
            id, descricao, valor_total, data_compra, parcelas, tipo_pagamento,
            cartao_id, conta_id, categoria_id, situacao
        )
        SELECT
            compra_id,
            regexp_replace(MIN(descricao), ' \\([0-9]+/[0-9]+\\)$', ''),
            SUM(valor), MIN(data), MAX(parcelas), MIN(tipo_pagamento),
            MIN(cartao_id), MIN(cartao_id), MIN(categoria_id), 'ativa'
        FROM gasto_diarios
        WHERE compra_id IS NOT NULL
        GROUP BY compra_id
        """
    )
    op.create_foreign_key(
        "fk_gasto_diarios_compra", "gasto_diarios", "compras", ["compra_id"], ["id"], ondelete="RESTRICT"
    )

    for tabela in ("gasto_diarios", "receitas", "aportes_reserva"):
        op.add_column(tabela, sa.Column("conta_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{tabela}_conta", tabela, "contas", ["conta_id"], ["id"], ondelete="RESTRICT"
        )
        op.create_index(f"ix_{tabela}_conta_id", tabela, ["conta_id"])
        op.execute(f"UPDATE {tabela} SET conta_id = cartao_id WHERE cartao_id IS NOT NULL")

    op.alter_column("gasto_diarios", "cartao_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("receitas", "cartao_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("aportes_reserva", "cartao_id", existing_type=sa.Integer(), nullable=True)

    op.add_column("pagamentos_fatura", sa.Column("conta_id", sa.Integer(), nullable=True))
    op.add_column("pagamentos_fatura", sa.Column("estornado_em", sa.DateTime(timezone=True), nullable=True))
    op.add_column("pagamentos_fatura", sa.Column("estorno_idempotency_key", sa.String(120), nullable=True))
    op.add_column("pagamentos_fatura", sa.Column("motivo_estorno", sa.String(255), nullable=True))
    op.create_foreign_key(
        "fk_pagamentos_fatura_conta", "pagamentos_fatura", "contas", ["conta_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index("ix_pagamentos_fatura_conta_id", "pagamentos_fatura", ["conta_id"])
    op.create_index(
        "ix_pagamentos_fatura_estorno_idempotency_key",
        "pagamentos_fatura",
        ["estorno_idempotency_key"],
        unique=True,
    )
    op.execute("UPDATE pagamentos_fatura SET conta_id = cartao_id WHERE movimentou_saldo IS TRUE")

    op.create_table(
        "alocacoes_pagamento_fatura",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pagamento_id", sa.Integer(), nullable=False),
        sa.Column("gasto_id", sa.Integer(), nullable=False),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.ForeignKeyConstraint(["pagamento_id"], ["pagamentos_fatura.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["gasto_id"], ["gasto_diarios.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("pagamento_id", "gasto_id", name="uq_alocacao_pagamento_gasto"),
    )
    op.create_index("ix_alocacoes_pagamento_fatura_id", "alocacoes_pagamento_fatura", ["id"])
    op.create_index("ix_alocacoes_pagamento_fatura_pagamento_id", "alocacoes_pagamento_fatura", ["pagamento_id"])
    op.create_index("ix_alocacoes_pagamento_fatura_gasto_id", "alocacoes_pagamento_fatura", ["gasto_id"])

    op.create_table(
        "reembolsos_compra",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("compra_id", sa.String(36), nullable=False),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.Column("motivo", sa.String(255), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("idempotency_key", sa.String(120), nullable=True),
        sa.ForeignKeyConstraint(["compra_id"], ["compras.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("idempotency_key", name="uq_reembolsos_compra_idempotency_key"),
    )
    op.create_index("ix_reembolsos_compra_id", "reembolsos_compra", ["id"])
    op.create_index("ix_reembolsos_compra_compra_id", "reembolsos_compra", ["compra_id"])
    op.create_index("ix_reembolsos_compra_idempotency_key", "reembolsos_compra", ["idempotency_key"], unique=True)

    op.create_table(
        "transferencias",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conta_origem_id", sa.Integer(), nullable=False),
        sa.Column("conta_destino_id", sa.Integer(), nullable=False),
        sa.Column("descricao", sa.String(255), nullable=False, server_default="Transferencia"),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.Column("data", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=True),
        sa.Column("estornada_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conta_origem_id"], ["contas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["conta_destino_id"], ["contas.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("idempotency_key", name="uq_transferencias_idempotency_key"),
    )
    for coluna in ("id", "conta_origem_id", "conta_destino_id", "data", "idempotency_key"):
        op.create_index(f"ix_transferencias_{coluna}", "transferencias", [coluna], unique=coluna == "idempotency_key")

    op.create_table(
        "metas_reserva",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("dono", sa.String(80), nullable=False, server_default="Eu"),
        sa.Column("valor_alvo", sa.Numeric(12, 2), nullable=False),
        sa.Column("saldo", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("prazo", sa.Date(), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_metas_reserva_id", "metas_reserva", ["id"])
    op.add_column("aportes_reserva", sa.Column("meta_id", sa.Integer(), nullable=True))
    op.add_column("aportes_reserva", sa.Column("tipo", sa.String(20), nullable=False, server_default="aporte"))
    op.create_foreign_key(
        "fk_aportes_reserva_meta", "aportes_reserva", "metas_reserva", ["meta_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_aportes_reserva_meta_id", "aportes_reserva", ["meta_id"])

    op.create_table(
        "orcamentos_categoria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("categoria_id", sa.Integer(), nullable=False),
        sa.Column("dono", sa.String(80), nullable=False, server_default="Eu"),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column("ano", sa.Integer(), nullable=False),
        sa.Column("limite", sa.Numeric(12, 2), nullable=False),
        sa.Column("alerta_percentual", sa.Integer(), nullable=False, server_default="80"),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("categoria_id", "dono", "mes", "ano", name="uq_orcamento_categoria_competencia"),
    )
    op.create_index("ix_orcamentos_categoria_id", "orcamentos_categoria", ["id"])
    op.create_index("ix_orcamentos_categoria_categoria_id", "orcamentos_categoria", ["categoria_id"])

    op.create_table(
        "recorrencias",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tipo_lancamento", sa.String(20), nullable=False),
        sa.Column("descricao", sa.String(255), nullable=False),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.Column("dia_mes", sa.Integer(), nullable=False),
        sa.Column("proxima_data", sa.Date(), nullable=False),
        sa.Column("conta_id", sa.Integer(), nullable=True),
        sa.Column("cartao_id", sa.Integer(), nullable=True),
        sa.Column("categoria_id", sa.Integer(), nullable=True),
        sa.Column("tipo_pagamento", sa.String(20), nullable=True),
        sa.Column("parcelas", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["conta_id"], ["contas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cartao_id"], ["cartoes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_recorrencias_id", "recorrencias", ["id"])
    op.create_index("ix_recorrencias_proxima_data", "recorrencias", ["proxima_data"])
    op.create_table(
        "execucoes_recorrencia",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recorrencia_id", sa.Integer(), nullable=False),
        sa.Column("data_prevista", sa.Date(), nullable=False),
        sa.Column("entidade", sa.String(20), nullable=False),
        sa.Column("entidade_id", sa.Integer(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["recorrencia_id"], ["recorrencias.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("recorrencia_id", "data_prevista", name="uq_execucao_recorrencia_data"),
    )
    op.create_index("ix_execucoes_recorrencia_id", "execucoes_recorrencia", ["id"])
    op.create_index("ix_execucoes_recorrencia_recorrencia_id", "execucoes_recorrencia", ["recorrencia_id"])


def downgrade() -> None:
    op.drop_table("execucoes_recorrencia")
    op.drop_table("recorrencias")
    op.drop_table("orcamentos_categoria")
    op.drop_constraint("fk_aportes_reserva_meta", "aportes_reserva", type_="foreignkey")
    op.drop_column("aportes_reserva", "tipo")
    op.drop_column("aportes_reserva", "meta_id")
    op.drop_table("metas_reserva")
    op.drop_table("transferencias")
    op.drop_table("reembolsos_compra")
    op.drop_table("alocacoes_pagamento_fatura")
    for coluna in ("motivo_estorno", "estorno_idempotency_key", "estornado_em"):
        op.drop_column("pagamentos_fatura", coluna)
    op.drop_constraint("fk_pagamentos_fatura_conta", "pagamentos_fatura", type_="foreignkey")
    op.drop_column("pagamentos_fatura", "conta_id")
    for tabela in ("aportes_reserva", "receitas", "gasto_diarios"):
        op.alter_column(tabela, "cartao_id", existing_type=sa.Integer(), nullable=False)
        op.drop_constraint(f"fk_{tabela}_conta", tabela, type_="foreignkey")
        op.drop_column(tabela, "conta_id")
    op.drop_constraint("fk_gasto_diarios_compra", "gasto_diarios", type_="foreignkey")
    op.drop_table("compras")
    op.drop_constraint("fk_cartoes_conta_padrao", "cartoes", type_="foreignkey")
    op.drop_column("cartoes", "conta_padrao_id")
    op.drop_column("cartoes", "limite_total")
    op.drop_table("contas")
    op.drop_index("uq_categorias_nome_normalizado", table_name="categorias")
    op.alter_column("categorias", "nome", existing_type=sa.String(), nullable=True)
