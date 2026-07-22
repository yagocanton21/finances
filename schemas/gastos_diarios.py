from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class GastoDiarioBase(BaseModel):
    descricao: str
    valor: float
    data: datetime
    categoria_id: Optional[int] = None
    cartao_id: int
    tipo_pagamento: str
    parcelas: int = 1
    
class GastoDiarioCreate(GastoDiarioBase):
    pass

class GastoDiarioUpdate(GastoDiarioBase):
    pass

class GastoDiarioInDb(GastoDiarioBase):
    id: int

    model_config = ConfigDict(from_attributes=True)