from database import Base
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

class Categoria(Base):
    __tablename__ = 'categorias'
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    gastos = relationship("GastoDiario", back_populates="categoria")
