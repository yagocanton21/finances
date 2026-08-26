from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from database import Base


class Cartao(Base):
    __tablename__ = "cartoes"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    dono = Column(String, nullable=False, default="Eu")
    limite = Column(Numeric(12, 2), nullable=False, default=0)
    limite_total = Column(Numeric(12, 2), nullable=False, default=0)
    saldo = Column(Numeric(12, 2), nullable=False, default=0)
    conta_padrao_id = Column(
        Integer, ForeignKey("contas.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    data_fatura = Column(Integer, nullable=False)
    dia_vencimento = Column(Integer, nullable=False)
    fatura_atual = Column(Numeric(12, 2), nullable=False, default=0)
    ativo = Column(Boolean, nullable=False, default=True, server_default="true")
    gastos = relationship("GastoDiario", back_populates="cartao", passive_deletes=True)
    receitas = relationship("Receita", back_populates="cartao", passive_deletes=True)
    aportes_reserva = relationship("AporteReserva", back_populates="cartao", passive_deletes=True)
    faturas = relationship("Fatura", back_populates="cartao", passive_deletes=True)
    pagamentos_fatura = relationship(
        "PagamentoFatura", back_populates="cartao", passive_deletes=True
    )
    conta_padrao = relationship("Conta", back_populates="cartoes")
