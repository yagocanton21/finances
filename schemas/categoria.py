from pydantic import BaseModel, ConfigDict

class CategoriaBase(BaseModel):
    nome: str
    
class CategoriaCreate(CategoriaBase):
    pass

class CategoriaUpdate(CategoriaBase):
    pass

class CategoriaInDb(CategoriaBase):
    id: int

    model_config = ConfigDict(from_attributes=True)