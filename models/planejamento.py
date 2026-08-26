from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from database import Base


class Recorrencia(Base):
    __tablename__ = "recorrencias"

    id = Column(Integer, primary_key=True, index=True)
    tipo_lancamento = Column(String(20), nullable=False)
    descricao = Column(String(255), nullable=False)
    valor = Column(Numeric(12, 2), nullable=False)
    dia_mes = Column(Integer, nullable=False)
    proxima_data = Column(Date, nullable=False, index=True)
    conta_id = Column(Integer, ForeignKey("contas.id", ondelete="RESTRICT"), nullable=True)
    cartao_id = Column(Integer, ForeignKey("cartoes.id", ondelete="RESTRICT"), nullable=True)
    categoria_id = Column(Integer, ForeignKey("categorias.id", ondelete="SET NULL"), nullable=True)
    tipo_pagamento = Column(String(20), nullable=True)
    parcelas = Column(Integer, nullable=False, default=1)
    ativa = Column(Boolean, nullable=False, default=True, server_default="true")
    criada_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ExecucaoRecorrencia(Base):
    __tablename__ = "execucoes_recorrencia"
    __table_args__ = (
        UniqueConstraint("recorrencia_id", "data_prevista", name="uq_execucao_recorrencia_data"),
    )

    id = Column(Integer, primary_key=True, index=True)
    recorrencia_id = Column(
        Integer, ForeignKey("recorrencias.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    data_prevista = Column(Date, nullable=False)
    entidade = Column(String(20), nullable=False)
    entidade_id = Column(Integer, nullable=False)
    criada_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class OrcamentoCategoria(Base):
    __tablename__ = "orcamentos_categoria"
    __table_args__ = (
        UniqueConstraint(
            "categoria_id", "dono", "mes", "ano", name="uq_orcamento_categoria_competencia"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    categoria_id = Column(
        Integer, ForeignKey("categorias.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dono = Column(String(80), nullable=False, default="Eu")
    mes = Column(Integer, nullable=False)
    ano = Column(Integer, nullable=False)
    limite = Column(Numeric(12, 2), nullable=False)
    alerta_percentual = Column(Integer, nullable=False, default=80)


class MetaReserva(Base):
    __tablename__ = "metas_reserva"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(120), nullable=False)
    dono = Column(String(80), nullable=False, default="Eu")
    valor_alvo = Column(Numeric(12, 2), nullable=False)
    saldo = Column(Numeric(12, 2), nullable=False, default=0)
    prazo = Column(Date, nullable=True)
    ativa = Column(Boolean, nullable=False, default=True, server_default="true")
    criada_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    movimentos = relationship("AporteReserva", back_populates="meta")
