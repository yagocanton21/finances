from sqlalchemy import Column, DateTime, Integer, JSON, String, func

from database import Base


class AuditoriaAgente(Base):
    __tablename__ = "auditoria_agente"

    id = Column(Integer, primary_key=True)
    external_id = Column(String(120), nullable=False, unique=True, index=True)
    agente = Column(String(80), nullable=False, default="hermes")
    acao = Column(String(40), nullable=False)
    entidade = Column(String(40), nullable=False)
    entidade_id = Column(Integer, nullable=True)
    status = Column(String(30), nullable=False)
    requisicao = Column(JSON, nullable=False)
    resposta = Column(JSON, nullable=False)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
