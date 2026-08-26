from datetime import datetime
from decimal import Decimal

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AporteReservaBase(BaseModel):
    descricao: str = Field(min_length=1, max_length=255)
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    data: datetime
    cartao_id: Optional[int] = Field(default=None, gt=0)
    conta_id: Optional[int] = Field(default=None, gt=0)
    meta_id: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validar_conta(self):
        if not (self.cartao_id or self.conta_id):
            raise ValueError("Informe conta_id ou cartao_id")
        return self


class AporteReservaInDb(AporteReservaBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
