"""repair items marked paid without an invoice payment

Revision ID: c4d5e6f7a8b9
Revises: f1a2b3c4d5e6
Create Date: 2026-08-12
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A parcela so pode permanecer paga quando existe pagamento registrado
    # para a competencia atual da respectiva conta. Isso corrige flags antigas
    # sem reabrir parcelas de faturas que realmente foram quitadas.
    op.execute(
        """
        WITH competencia_atual AS (
            SELECT
                c.id AS cartao_id,
                date_trunc('month', CURRENT_DATE)
                    + CASE
                        WHEN EXTRACT(DAY FROM CURRENT_DATE) >= c.data_fatura
                        THEN INTERVAL '2 months'
                        ELSE INTERVAL '1 month'
                      END AS referencia
            FROM cartoes c
            WHERE c.ativo IS TRUE
        )
        UPDATE gasto_diarios g
        SET pago = FALSE
        FROM competencia_atual ca
        WHERE g.cartao_id = ca.cartao_id
          AND g.tipo_pagamento = 'credito'
          AND g.pago IS TRUE
          AND date_trunc('month', g.data)
                + CASE
                    WHEN EXTRACT(DAY FROM g.data) >= (
                        SELECT c.data_fatura
                        FROM cartoes c
                        WHERE c.id = g.cartao_id
                    )
                    THEN INTERVAL '2 months'
                    ELSE INTERVAL '1 month'
                  END = ca.referencia
          AND NOT EXISTS (
              SELECT 1
              FROM pagamentos_fatura p
              WHERE p.cartao_id = ca.cartao_id
                AND p.mes_ref = EXTRACT(MONTH FROM ca.referencia)::INTEGER
                AND p.ano_ref = EXTRACT(YEAR FROM ca.referencia)::INTEGER
          )
        """
    )


def downgrade() -> None:
    # Nao e seguro re-marcar como pagas parcelas sem saber quais estavam
    # incorretas antes da migration.
    pass
