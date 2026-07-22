from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Categoria, Cartao, GastoDiario
from schemas import CategoriaBase, CartaoBase, GastoDiarioBase

router = APIRouter()

@router.post('/')
def criar_cartao(cartao_in: CartaoBase, db: Session = Depends(get_db)):
    try:
        dados_cartao = cartao_in.dict() if hasattr(cartao_in, 'dict') else cartao_in.model_dump()
        db_cartao = Cartao(**dados_cartao)
        db.add(db_cartao)
        db.commit()
        db.refresh(db_cartao)
        return db_cartao
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Erro ao criar cartao: {str(e)}')

@router.get('/')
def listar_cartoes(db: Session = Depends(get_db)):
    try:
        cartoes = db.query(Cartao).all()
        return cartoes
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Erro ao listar cartoes: {str(e)}')

@router.get('/{id}')
def buscar_cartao(id: int, db: Session = Depends(get_db)):
    try:
        db_cartao = db.query(Cartao).filter(Cartao.id == id).first()
        if not db_cartao:
            raise HTTPException(status_code=404, detail='Cartão não encontrado')
        return db_cartao
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Erro ao buscar cartao: {str(e)}')

@router.put('/{id}')
def atualizar_cartao(id: int, cartao_in: CartaoBase, db: Session = Depends(get_db)):
    try:
        db_cartao = db.query(Cartao).filter(Cartao.id == id).first()
        if not db_cartao:
            raise HTTPException(status_code=404, detail='Cartão não encontrado')
        
        # Atribuindo os novos valores ao objeto do banco de dados
        db_cartao.nome = cartao_in.nome
        db_cartao.limite = cartao_in.limite
        db_cartao.saldo = cartao_in.saldo
        db_cartao.data_fatura = cartao_in.data_fatura
        db_cartao.dia_vencimento = cartao_in.dia_vencimento
        db_cartao.fatura_atual = cartao_in.fatura_atual
        
        db.commit()
        db.refresh(db_cartao)
        return db_cartao
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Erro ao atualizar cartao: {str(e)}')

@router.delete('/{id}')
def deletar_cartao(id: int, db: Session = Depends(get_db)):
    try:
        db_cartao = db.query(Cartao).filter(Cartao.id == id).first()
        if not db_cartao:
            raise HTTPException(status_code=404, detail='Cartão não encontrado')
        
        db.delete(db_cartao)
        db.commit()
        return {'mensagem': 'Cartão deletado com sucesso'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Erro ao deletar cartao: {str(e)}')

@router.post('/{id}/pagar_fatura')
def pagar_fatura(id: int, db: Session = Depends(get_db)):
    try:
        cartao = db.query(Cartao).filter(Cartao.id == id).first()
        if not cartao:
            raise HTTPException(status_code=404, detail='Cartão não encontrado')
            
        valor_fatura = cartao.fatura_atual
        
        # 1. Paga a fatura
        cartao.saldo -= valor_fatura
        cartao.limite += valor_fatura
        cartao.fatura_atual = 0
        
        # 2. Puxa as parcelas do próximo mês
        from datetime import datetime, timedelta
        hoje = datetime.now()
        daqui_30_dias = hoje + timedelta(days=30)
        
        # Busca gastos futuros desse cartão no crédito
        gastos_futuros = db.query(GastoDiario).filter(
            GastoDiario.cartao_id == id,
            GastoDiario.tipo_pagamento.ilike('credito'),
            GastoDiario.data > hoje,
            GastoDiario.data <= daqui_30_dias
        ).all()
        
        valor_proximo_mes = sum(g.valor for g in gastos_futuros)
        cartao.fatura_atual += valor_proximo_mes
        
        db.commit()
        db.refresh(cartao)
        
        # Convertemos para dict para retornar
        return {
            "mensagem": "Fatura paga com sucesso!",
            "valor_pago": valor_fatura,
            "nova_fatura": cartao.fatura_atual,
            "novo_saldo": cartao.saldo,
            "novo_limite": cartao.limite
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Erro ao pagar fatura: {str(e)}')