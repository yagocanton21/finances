"""add savings contributions"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO categorias (nome)
        SELECT nome FROM (VALUES
            ('Alimentação'), ('Moradia'), ('Transporte'), ('Saúde'),
            ('Educação'), ('Lazer'), ('Assinaturas'), ('Compras'), ('Outros')
        ) AS padrao(nome)
        WHERE NOT EXISTS (
            SELECT 1 FROM categorias existente WHERE lower(existente.nome) = lower(padrao.nome)
        )
        """
    )
    op.create_table(
        "aportes_reserva",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("descricao", sa.String(255), nullable=False),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.Column("data", sa.DateTime(), nullable=False),
        sa.Column("cartao_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["cartao_id"], ["cartoes.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_aportes_reserva_id", "aportes_reserva", ["id"], unique=False)
    op.create_index("ix_aportes_reserva_data", "aportes_reserva", ["data"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_aportes_reserva_data", table_name="aportes_reserva")
    op.drop_index("ix_aportes_reserva_id", table_name="aportes_reserva")
    op.drop_table("aportes_reserva")
