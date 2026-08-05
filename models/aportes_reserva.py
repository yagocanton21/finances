from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from database import Base


class AporteReserva(Base):
    __tablename__ = "aportes_reserva"

    id = Column(Integer, primary_key=True, index=True)
    descricao = Column(String(255), nullable=False)
    valor = Column(Numeric(12, 2), nullable=False)
    data = Column(DateTime, nullable=False, index=True)
    cartao_id = Column(Integer, ForeignKey("cartoes.id", ondelete="RESTRICT"), nullable=False)

    cartao = relationship("Cartao", back_populates="aportes_reserva")
