from database import Base
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship

class Receita(Base):
    __tablename__ = 'receitas'
    
    id = Column(Integer, primary_key=True, index=True)
    descricao = Column(String, index=True)
    valor = Column(Float)
    data = Column(DateTime)
    categoria_id = Column(Integer, ForeignKey('categorias.id'), nullable=True) # Pode ser nulo
    cartao_id = Column(Integer, ForeignKey('cartoes.id')) # Conta/Cartão onde o dinheiro entrou
    
    categoria = relationship("Categoria")
    cartao = relationship("Cartao", back_populates="receitas")
