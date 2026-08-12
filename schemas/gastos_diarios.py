from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TipoPagamento(str, Enum):
    credito = "credito"
    debito = "debito"
    pix = "pix"


class GastoDiarioBase(BaseModel):
    descricao: str = Field(min_length=1, max_length=255)
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    data: datetime
    categoria_id: Optional[int] = None
    cartao_id: int = Field(gt=0)
    tipo_pagamento: TipoPagamento
    parcelas: int = Field(default=1, ge=1, le=120)

    @model_validator(mode="after")
    def validar_parcelamento(self):
        if self.tipo_pagamento != TipoPagamento.credito and self.parcelas != 1:
            raise ValueError("Parcelamento so e permitido para pagamentos em credito")
        return self


class GastoDiarioCreate(GastoDiarioBase):
    pass


class GastoDiarioUpdate(GastoDiarioBase):
    pass


class GastoDiarioPatch(BaseModel):
    descricao: Optional[str] = Field(default=None, min_length=1, max_length=255)
    valor: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    data: Optional[datetime] = None
    categoria_id: Optional[int] = None


class ConciliarPagamentoIn(BaseModel):
    """Ajusta apenas o histórico, sem movimentar saldo ou limite."""

    pago: bool


class GastoDiarioInDb(GastoDiarioBase):
    id: int
    pago: bool
    compra_id: Optional[str] = None
    numero_parcela: int = 1

    model_config = ConfigDict(from_attributes=True)
