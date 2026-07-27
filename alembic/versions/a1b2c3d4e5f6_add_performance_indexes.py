"""add_performance_indexes

Revision ID: a1b2c3d4e5f6
Revises: 25ebe6280a67
Create Date: 2026-07-27 00:16:00.000000

Adiciona índices nos campos de filtragem frequente da tabela gasto_diarios:
- data: filtrado por mês/ano em todas as listagens
- tipo_pagamento: filtrado no cálculo de faturas
- pago: filtrado no cálculo de faturas e listagem de gastos pendentes
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '3f6a2c81df51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria índices de performance na tabela gasto_diarios."""
    op.create_index('ix_gasto_diarios_data', 'gasto_diarios', ['data'], unique=False)
    op.create_index('ix_gasto_diarios_tipo_pagamento', 'gasto_diarios', ['tipo_pagamento'], unique=False)
    op.create_index('ix_gasto_diarios_pago', 'gasto_diarios', ['pago'], unique=False)


def downgrade() -> None:
    """Remove os índices de performance."""
    op.drop_index('ix_gasto_diarios_pago', table_name='gasto_diarios')
    op.drop_index('ix_gasto_diarios_tipo_pagamento', table_name='gasto_diarios')
    op.drop_index('ix_gasto_diarios_data', table_name='gasto_diarios')
