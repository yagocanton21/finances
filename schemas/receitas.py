from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class ReceitaBase(BaseModel):
    descricao: str
    valor: float
    data: datetime
    categoria_id: Optional[int] = None
    cartao_id: int

class ReceitaCreate(ReceitaBase):
    pass

class ReceitaUpdate(ReceitaBase):
    pass

class ReceitaInDb(ReceitaBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
