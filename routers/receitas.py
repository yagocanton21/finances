from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Receita, Cartao
from schemas.receitas import ReceitaBase

router = APIRouter()

@router.post('/')
def criar_receita(receita_in: ReceitaBase, db: Session = Depends(get_db)):
    try:
        dados = receita_in.dict() if hasattr(receita_in, 'dict') else receita_in.model_dump()
        db_receita = Receita(**dados)
        
        cartao = db.query(Cartao).filter(Cartao.id == db_receita.cartao_id).first()
        if not cartao:
            raise HTTPException(status_code=404, detail='Cartão/Conta não encontrada')
            
        # Adiciona o valor recebido ao saldo da conta
        cartao.saldo += db_receita.valor
        
        db.add(db_receita)
        db.commit()
        db.refresh(db_receita)
        return db_receita
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Erro ao criar receita: {str(e)}')

@router.get('/')
def listar_receitas(db: Session = Depends(get_db)):
    try:
        return db.query(Receita).all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Erro ao listar receitas: {str(e)}')

@router.get('/{id}')
def buscar_receita(id: int, db: Session = Depends(get_db)):
    try:
        db_receita = db.query(Receita).filter(Receita.id == id).first()
        if not db_receita:
            raise HTTPException(status_code=404, detail='Receita não encontrada')
        return db_receita
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Erro ao buscar receita: {str(e)}')

@router.put('/{id}')
def atualizar_receita(id: int, receita_in: ReceitaBase, db: Session = Depends(get_db)):
    try:
        db_receita = db.query(Receita).filter(Receita.id == id).first()
        if not db_receita:
            raise HTTPException(status_code=404, detail='Receita não encontrada')
            
        # 1. Estorno da receita antiga
        cartao_antigo = db.query(Cartao).filter(Cartao.id == db_receita.cartao_id).first()
        if cartao_antigo:
            cartao_antigo.saldo -= db_receita.valor
            
        # 2. Atualizar dados
        db_receita.descricao = receita_in.descricao
        db_receita.valor = receita_in.valor
        db_receita.data = receita_in.data
        db_receita.categoria_id = receita_in.categoria_id
        db_receita.cartao_id = receita_in.cartao_id
        
        # 3. Aplicar a nova receita
        cartao_novo = db.query(Cartao).filter(Cartao.id == db_receita.cartao_id).first()
        if not cartao_novo:
            raise HTTPException(status_code=404, detail='Nova Conta/Cartão não encontrada')
            
        cartao_novo.saldo += db_receita.valor
        
        db.commit()
        db.refresh(db_receita)
        return db_receita
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Erro ao atualizar receita: {str(e)}')

@router.delete('/{id}')
def deletar_receita(id: int, db: Session = Depends(get_db)):
    try:
        db_receita = db.query(Receita).filter(Receita.id == id).first()
        if not db_receita:
            raise HTTPException(status_code=404, detail='Receita não encontrada')
            
        cartao = db.query(Cartao).filter(Cartao.id == db_receita.cartao_id).first()
        if cartao:
            # Subtrai do saldo o dinheiro que havia entrado
            cartao.saldo -= db_receita.valor
            
        db.delete(db_receita)
        db.commit()
        return {'mensagem': 'Receita deletada com sucesso'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Erro ao deletar receita: {str(e)}')
