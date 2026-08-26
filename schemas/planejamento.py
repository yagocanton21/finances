from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from schemas.gastos_diarios import TipoPagamento


class RecorrenciaIn(BaseModel):
    tipo_lancamento: str = Field(pattern="^(gasto|receita)$")
    descricao: str = Field(min_length=1, max_length=255)
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    dia_mes: int = Field(ge=1, le=31)
    proxima_data: date
    conta_id: Optional[int] = Field(default=None, gt=0)
    cartao_id: Optional[int] = Field(default=None, gt=0)
    categoria_id: Optional[int] = Field(default=None, gt=0)
    tipo_pagamento: Optional[TipoPagamento] = None
    parcelas: int = Field(default=1, ge=1, le=120)

    @model_validator(mode="after")
    def validar_destino(self):
        if self.tipo_lancamento == "receita":
            if not self.conta_id or self.cartao_id or self.tipo_pagamento:
                raise ValueError("Receita recorrente requer conta_id")
            if self.parcelas != 1:
                raise ValueError("Receita nao pode ser parcelada")
        elif self.tipo_pagamento == TipoPagamento.credito:
            if not self.cartao_id:
                raise ValueError("Gasto recorrente no credito requer cartao_id")
        elif not self.conta_id:
            raise ValueError("Gasto recorrente requer conta_id")
        if self.tipo_pagamento != TipoPagamento.credito and self.parcelas != 1:
            raise ValueError("Parcelamento so e permitido no credito")
        return self


class OrcamentoIn(BaseModel):
    categoria_id: int = Field(gt=0)
    dono: str = Field(default="Eu", min_length=1, max_length=80)
    mes: int = Field(ge=1, le=12)
    ano: int = Field(ge=1900, le=2200)
    limite: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    alerta_percentual: int = Field(default=80, ge=1, le=100)


class MetaReservaIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    dono: str = Field(default="Eu", min_length=1, max_length=80)
    valor_alvo: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    prazo: Optional[date] = None


class MovimentoMetaIn(BaseModel):
    conta_id: int = Field(gt=0)
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    data: date
    descricao: str = Field(default="Movimento de reserva", min_length=1, max_length=255)
