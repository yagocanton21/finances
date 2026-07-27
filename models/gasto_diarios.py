from database import Base
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, Boolean
from sqlalchemy.orm import relationship

class GastoDiario(Base):
    __tablename__ = 'gasto_diarios'
    id = Column(Integer, primary_key=True, index=True)
    descricao = Column(String)
    valor = Column(Float)
    data = Column(DateTime, index=True)
    tipo_pagamento = Column(String, index=True)
    parcelas = Column(Integer)
    categoria_id = Column(Integer, ForeignKey('categorias.id'))
    cartao_id = Column(Integer, ForeignKey('cartoes.id'))
    pago = Column(Boolean, default=False, index=True)
    
    categoria = relationship("Categoria", back_populates="gastos")
    cartao = relationship("Cartao", back_populates="gastos")