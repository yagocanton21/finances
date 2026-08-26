from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app_logging import log_internal_error
from database import get_db
from models import Categoria
from schemas import CategoriaBase
from sqlalchemy.exc import IntegrityError

router = APIRouter()

@router.post('/')
def criar_categoria(categoria_in: CategoriaBase, db: Session = Depends(get_db)):
    try:
        dados_categoria = categoria_in.model_dump()
        db_categoria = Categoria(**dados_categoria)
        db.add(db_categoria)
        db.commit()
        db.refresh(db_categoria)
        return db_categoria
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Categoria ja cadastrada')
    except Exception:
        db.rollback()
        log_internal_error("criar_categoria")
        raise HTTPException(status_code=500, detail='Erro ao criar categoria')

@router.get('/')
def listar_categorias(db: Session = Depends(get_db)):
    try:
        return db.query(Categoria).all()
    except Exception:
        log_internal_error("listar_categorias")
        raise HTTPException(status_code=500, detail='Erro ao listar categorias')

@router.get('/{id}')
def buscar_categoria(id: int, db: Session = Depends(get_db)):
    try:
        db_categoria = db.query(Categoria).filter(Categoria.id == id).first()
        if not db_categoria:
            raise HTTPException(status_code=404, detail='Categoria não encontrada')
        return db_categoria
    except HTTPException:
        raise
    except Exception:
        log_internal_error("buscar_categoria")
        raise HTTPException(status_code=500, detail='Erro ao buscar categoria')

@router.put('/{id}')
def atualizar_categoria(id: int, categoria_in: CategoriaBase, db: Session = Depends(get_db)):
    try:
        db_categoria = db.query(Categoria).filter(Categoria.id == id).first()
        if not db_categoria:
            raise HTTPException(status_code=404, detail='Categoria não encontrada')
        
        db_categoria.nome = categoria_in.nome
        
        db.commit()
        db.refresh(db_categoria)
        return db_categoria
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Categoria ja cadastrada')
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        log_internal_error("atualizar_categoria")
        raise HTTPException(status_code=500, detail='Erro ao atualizar categoria')

@router.delete('/{id}')
def deletar_categoria(id: int, db: Session = Depends(get_db)):
    try:
        db_categoria = db.query(Categoria).filter(Categoria.id == id).first()
        if not db_categoria:
            raise HTTPException(status_code=404, detail='Categoria não encontrada')
        
        db.delete(db_categoria)
        db.commit()
        return {'mensagem': 'Categoria deletada com sucesso'}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        log_internal_error("deletar_categoria")
        raise HTTPException(status_code=500, detail='Erro ao deletar categoria')
