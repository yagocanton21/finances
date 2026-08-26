from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from database import Base


class Receita(Base):
    __tablename__ = "receitas"

    id = Column(Integer, primary_key=True, index=True)
    descricao = Column(String, nullable=False, index=True)
    valor = Column(Numeric(12, 2), nullable=False)
    data = Column(DateTime, nullable=False)
    categoria_id = Column(
        Integer, ForeignKey("categorias.id"), nullable=True
    )
    cartao_id = Column(
        Integer, ForeignKey("cartoes.id", ondelete="RESTRICT"), nullable=True
    )
    conta_id = Column(
        Integer, ForeignKey("contas.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    origem = Column(String(30), nullable=False, default="frontend", index=True)
    external_id = Column(String(120), nullable=True, index=True)

    categoria = relationship("Categoria")
    cartao = relationship("Cartao", back_populates="receitas")
    conta = relationship("Conta", back_populates="receitas")
