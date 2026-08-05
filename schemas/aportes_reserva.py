from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AporteReservaBase(BaseModel):
    descricao: str = Field(min_length=1, max_length=255)
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    data: datetime
    cartao_id: int = Field(gt=0)


class AporteReservaInDb(AporteReservaBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
