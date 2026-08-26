from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import relationship

from database import Base


class Compra(Base):
    __tablename__ = "compras"

    id = Column(String(36), primary_key=True)
    descricao = Column(String(255), nullable=False)
    valor_total = Column(Numeric(12, 2), nullable=False)
    valor_reembolsado = Column(Numeric(12, 2), nullable=False, default=0)
    data_compra = Column(DateTime, nullable=False, index=True)
    parcelas = Column(Integer, nullable=False, default=1)
    tipo_pagamento = Column(String(20), nullable=False)
    cartao_id = Column(
        Integer, ForeignKey("cartoes.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    conta_id = Column(
        Integer, ForeignKey("contas.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    categoria_id = Column(
        Integer, ForeignKey("categorias.id", ondelete="SET NULL"), nullable=True
    )
    situacao = Column(String(20), nullable=False, default="ativa")
    criada_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    itens = relationship("GastoDiario", back_populates="compra")
    reembolsos = relationship(
        "ReembolsoCompra", back_populates="compra", cascade="all, delete-orphan"
    )


class ReembolsoCompra(Base):
    __tablename__ = "reembolsos_compra"

    id = Column(Integer, primary_key=True, index=True)
    compra_id = Column(
        String(36), ForeignKey("compras.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    valor = Column(Numeric(12, 2), nullable=False)
    motivo = Column(String(255), nullable=False)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    idempotency_key = Column(String(120), nullable=True, unique=True, index=True)

    compra = relationship("Compra", back_populates="reembolsos")
