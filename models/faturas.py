from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base


class Fatura(Base):
    __tablename__ = "faturas"
    __table_args__ = (
        UniqueConstraint(
            "cartao_id", "mes_ref", "ano_ref", name="uq_faturas_cartao_competencia"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    cartao_id = Column(
        Integer, ForeignKey("cartoes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    mes_ref = Column(Integer, nullable=False)
    ano_ref = Column(Integer, nullable=False)
    total = Column(Numeric(12, 2), nullable=False, default=0)
    situacao = Column(String(20), nullable=False, default="aberta")
    criada_em = Column(DateTime(timezone=True), nullable=False)

    cartao = relationship("Cartao", back_populates="faturas")
    pagamentos = relationship(
        "PagamentoFatura", back_populates="fatura", cascade="all, delete-orphan"
    )


class PagamentoFatura(Base):
    __tablename__ = "pagamentos_fatura"

    id = Column(Integer, primary_key=True, index=True)
    fatura_id = Column(
        Integer, ForeignKey("faturas.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    cartao_id = Column(
        Integer, ForeignKey("cartoes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    mes_ref = Column(Integer, nullable=False)
    ano_ref = Column(Integer, nullable=False)
    valor = Column(Numeric(12, 2), nullable=False)
    data_pagamento = Column(DateTime(timezone=True), nullable=False)
    situacao = Column(String(20), nullable=False)
    origem = Column(String(20), nullable=False, default="sistema", server_default="sistema")
    movimentou_saldo = Column(Boolean, nullable=False, default=True, server_default="true")
    idempotency_key = Column(String(120), nullable=True, unique=True, index=True)

    fatura = relationship("Fatura", back_populates="pagamentos")
    cartao = relationship("Cartao", back_populates="pagamentos_fatura")
