from database import Base
from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import relationship

class Cartao(Base):
    __tablename__ = 'cartoes'
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    dono = Column(String, default="Eu") # Quem é o dono da conta (Ex: Eu, Vô)
    limite = Column(Float)
    saldo = Column(Float)
    data_fatura = Column(Integer)
    dia_vencimento = Column(Integer)
    fatura_atual = Column(Float)
    gastos = relationship("GastoDiario", back_populates="cartao")
    receitas = relationship("Receita", back_populates="cartao")