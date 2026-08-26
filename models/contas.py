from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import relationship

from database import Base


class Conta(Base):
    __tablename__ = "contas"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(120), nullable=False)
    dono = Column(String(80), nullable=False, default="Eu")
    tipo = Column(String(20), nullable=False, default="corrente")
    saldo = Column(Numeric(12, 2), nullable=False, default=0)
    ativa = Column(Boolean, nullable=False, default=True, server_default="true")
    criada_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    cartoes = relationship("Cartao", back_populates="conta_padrao")
    receitas = relationship("Receita", back_populates="conta")
    gastos = relationship("GastoDiario", back_populates="conta")
    aportes_reserva = relationship("AporteReserva", back_populates="conta")
    transferencias_origem = relationship(
        "Transferencia",
        foreign_keys="Transferencia.conta_origem_id",
        back_populates="conta_origem",
    )
    transferencias_destino = relationship(
        "Transferencia",
        foreign_keys="Transferencia.conta_destino_id",
        back_populates="conta_destino",
    )


class Transferencia(Base):
    __tablename__ = "transferencias"

    id = Column(Integer, primary_key=True, index=True)
    conta_origem_id = Column(
        Integer, ForeignKey("contas.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    conta_destino_id = Column(
        Integer, ForeignKey("contas.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    descricao = Column(String(255), nullable=False, default="Transferencia")
    valor = Column(Numeric(12, 2), nullable=False)
    data = Column(DateTime(timezone=True), nullable=False, index=True)
    idempotency_key = Column(String(120), nullable=True, unique=True, index=True)
    estornada_em = Column(DateTime(timezone=True), nullable=True)

    conta_origem = relationship(
        "Conta", foreign_keys=[conta_origem_id], back_populates="transferencias_origem"
    )
    conta_destino = relationship(
        "Conta", foreign_keys=[conta_destino_id], back_populates="transferencias_destino"
    )
