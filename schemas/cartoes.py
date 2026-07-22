from pydantic import BaseModel, ConfigDict

class CartaoBase(BaseModel):
    nome: str
    dono: str = "Eu"
    limite: float
    saldo: float
    data_fatura: int
    dia_vencimento: int
    fatura_atual: float
    
class CartaoCreate(CartaoBase):
    pass

class CartaoUpdate(CartaoBase):
    pass

class CartaoInDb(CartaoBase):
    id: int

    model_config = ConfigDict(from_attributes=True)