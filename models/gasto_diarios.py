from database import Base
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, Boolean
from sqlalchemy.orm import relationship

class GastoDiario(Base):
    __tablename__ = 'gasto_diarios'
    id = Column(Integer, primary_key=True, index=True)
    descricao = Column(String)
    valor = Column(Float)
    data = Column(DateTime)
    tipo_pagamento = Column(String)
    parcelas = Column(Integer)
    categoria_id = Column(Integer, ForeignKey('categorias.id'))
    cartao_id = Column(Integer, ForeignKey('cartoes.id'))
    pago = Column(Boolean, default=False)
    
    categoria = relationship("Categoria", back_populates="gastos")
    cartao = relationship("Cartao", back_populates="gastos")