from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ReembolsoCompraIn(BaseModel):
    valor: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    motivo: str = Field(min_length=1, max_length=255)
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=120)


class AtualizarCompraIn(BaseModel):
    descricao: Optional[str] = Field(default=None, min_length=1, max_length=255)
    categoria_id: Optional[int] = Field(default=None, gt=0)
