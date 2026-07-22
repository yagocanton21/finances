from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Categoria
from schemas import CategoriaBase

router = APIRouter()

@router.post('/')
def criar_categoria(categoria_in: CategoriaBase, db: Session = Depends(get_db)):
    try:
        dados_categoria = categoria_in.dict() if hasattr(categoria_in, 'dict') else categoria_in.model_dump()
        db_categoria = Categoria(**dados_categoria)
        db.add(db_categoria)
        db.commit()
        db.refresh(db_categoria)
        return db_categoria
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Erro ao criar categoria: {str(e)}')

@router.get('/')
def listar_categorias(db: Session = Depends(get_db)):
    try:
        return db.query(Categoria).all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Erro ao listar categorias: {str(e)}')

@router.get('/{id}')
def buscar_categoria(id: int, db: Session = Depends(get_db)):
    try:
        db_categoria = db.query(Categoria).filter(Categoria.id == id).first()
        if not db_categoria:
            raise HTTPException(status_code=404, detail='Categoria não encontrada')
        return db_categoria
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Erro ao buscar categoria: {str(e)}')

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
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Erro ao atualizar categoria: {str(e)}')

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
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Erro ao deletar categoria: {str(e)}')
