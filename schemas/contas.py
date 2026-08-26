from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContaBase(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    dono: str = Field(default="Eu", min_length=1, max_length=80)
    tipo: str = Field(default="corrente", pattern="^(corrente|poupanca|dinheiro|investimento)$")
    saldo: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)


class ContaInDb(ContaBase):
    id: int
    ativa: bool
    model_config = ConfigDict(from_attributes=True)


class TransferenciaIn(BaseModel):
    conta_origem_id: int = Field(gt=0)
    conta_destino_id: int = Field(gt=0)
    descricao: str = Field(default="Transferencia", min_length=1, max_length=255)
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    data: datetime
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def validar_contas(self):
        if self.conta_origem_id == self.conta_destino_id:
            raise ValueError("Conta de origem e destino devem ser diferentes")
        return self


class EstornoIn(BaseModel):
    motivo: str = Field(default="Correcao de lancamento", min_length=1, max_length=255)
    idempotency_key: str = Field(min_length=1, max_length=120)
