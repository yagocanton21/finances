from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ReceitaBase(BaseModel):
    descricao: str = Field(min_length=1, max_length=255)
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    data: datetime
    categoria_id: Optional[int] = None
    cartao_id: int = Field(gt=0)


class ReceitaCreate(ReceitaBase):
    pass


class ReceitaUpdate(ReceitaBase):
    pass


class ReceitaInDb(ReceitaBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
