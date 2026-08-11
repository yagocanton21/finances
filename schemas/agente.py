from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from schemas.gastos_diarios import TipoPagamento


class TipoLancamento(str, Enum):
    gasto = "gasto"
    receita = "receita"


class LancamentoAgenteIn(BaseModel):
    tipo_lancamento: TipoLancamento
    descricao: str = Field(min_length=1, max_length=255)
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    data: datetime
    conta_id: Optional[int] = Field(default=None, gt=0)
    conta: Optional[str] = Field(default=None, min_length=1, max_length=120)
    categoria_id: Optional[int] = Field(default=None, gt=0)
    categoria: Optional[str] = Field(default=None, min_length=1, max_length=120)
    tipo_pagamento: Optional[TipoPagamento] = None
    parcelas: int = Field(default=1, ge=1, le=120)
    external_id: Optional[str] = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def validar_lancamento(self):
        if bool(self.conta_id) == bool(self.conta):
            raise ValueError("Informe exatamente um entre conta_id e conta")
        if self.categoria_id and self.categoria:
            raise ValueError("Informe apenas categoria_id ou categoria")
        if self.tipo_lancamento == TipoLancamento.gasto:
            if self.tipo_pagamento is None:
                raise ValueError("tipo_pagamento e obrigatorio para gastos")
            if self.tipo_pagamento != TipoPagamento.credito and self.parcelas != 1:
                raise ValueError("Parcelamento so e permitido no credito")
        elif self.tipo_pagamento is not None or self.parcelas != 1:
            raise ValueError("Receitas nao aceitam tipo_pagamento ou parcelas")
        return self


class PagamentoFaturaAgenteIn(BaseModel):
    conta_id: Optional[int] = Field(default=None, gt=0)
    conta: Optional[str] = Field(default=None, min_length=1, max_length=120)
    valor: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    mes_ref: Optional[int] = Field(default=None, ge=1, le=12)
    ano_ref: Optional[int] = Field(default=None, ge=1900, le=2200)
    confirmado: bool = False
    external_id: Optional[str] = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def validar_pagamento(self):
        if bool(self.conta_id) == bool(self.conta):
            raise ValueError("Informe exatamente um entre conta_id e conta")
        if self.ano_ref is not None and self.mes_ref is None:
            raise ValueError("ano_ref requer mes_ref")
        return self
