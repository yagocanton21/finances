from pydantic import BaseModel, ConfigDict, Field, field_validator

class CategoriaBase(BaseModel):
    nome: str = Field(min_length=1, max_length=120)

    @field_validator("nome")
    @classmethod
    def normalizar_nome(cls, valor: str) -> str:
        normalizado = " ".join(valor.split())
        if not normalizado:
            raise ValueError("Nome da categoria e obrigatorio")
        return normalizado
    
class CategoriaCreate(CategoriaBase):
    pass

class CategoriaUpdate(CategoriaBase):
    pass

class CategoriaInDb(CategoriaBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
