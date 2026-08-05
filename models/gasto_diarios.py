from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from database import Base


class GastoDiario(Base):
    __tablename__ = "gasto_diarios"

    id = Column(Integer, primary_key=True, index=True)
    descricao = Column(String, nullable=False)
    valor = Column(Numeric(12, 2), nullable=False)
    data = Column(DateTime, nullable=False, index=True)
    tipo_pagamento = Column(String, nullable=False, index=True)
    parcelas = Column(Integer, nullable=False, default=1)
    compra_id = Column(String(36), nullable=True, index=True)
    numero_parcela = Column(Integer, nullable=False, default=1)
    categoria_id = Column(Integer, ForeignKey("categorias.id"), nullable=True)
    cartao_id = Column(
        Integer, ForeignKey("cartoes.id", ondelete="RESTRICT"), nullable=False
    )
    pago = Column(Boolean, nullable=False, default=False, index=True)
    origem = Column(String(30), nullable=False, default="frontend", index=True)
    external_id = Column(String(120), nullable=True, index=True)

    categoria = relationship("Categoria", back_populates="gastos")
    cartao = relationship("Cartao", back_populates="gastos")
