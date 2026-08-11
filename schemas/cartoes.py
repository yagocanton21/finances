from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CartaoBase(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    dono: str = Field(default="Eu", min_length=1, max_length=80)
    limite: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    saldo: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    data_fatura: int = Field(ge=1, le=31)
    dia_vencimento: int = Field(ge=1, le=31)
    fatura_atual: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=12, decimal_places=2
    )
    ativo: bool = Field(default=True)


class CartaoCreate(CartaoBase):
    pass


class CartaoUpdate(CartaoBase):
    pass


class CartaoInDb(CartaoBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class PagarFaturaIn(BaseModel):
    valor: Optional[Decimal] = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    mes_ref: Optional[int] = Field(default=None, ge=1, le=12)
    ano_ref: Optional[int] = Field(default=None, ge=1900, le=2200)
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=120)
