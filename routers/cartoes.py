from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import pytz
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
        
        fuso = pytz.timezone("America/Sao_Paulo")
        hoje = datetime.now(fuso)
        
        resultado = []
        for c in cartoes:
            # Converte pra dict pra não sujar o banco de dados
            cartao_dict = c.__dict__.copy()
            if '_sa_instance_state' in cartao_dict:
                del cartao_dict['_sa_instance_state']
                
            gastos = db.query(GastoDiario).filter(
                GastoDiario.cartao_id == c.id,
                GastoDiario.tipo_pagamento == 'credito',
                GastoDiario.pago == False
            ).all()
            
            fatura_calc = 0.0
            dia_fechamento = c.data_fatura if c.data_fatura else 15
            for g in gastos:
                d = g.data
                mes_fatura = d.month - 1
                ano_fatura = d.year
                
                if d.day > dia_fechamento:
                    mes_fatura += 1
                    if mes_fatura > 11:
                        mes_fatura = 0
                        ano_fatura += 1
                        
                if mes_fatura == (hoje.month - 1) and ano_fatura == hoje.year:
                    fatura_calc += g.valor
                    
            cartao_dict['fatura_atual'] = round(fatura_calc, 2)
            resultado.append(cartao_dict)
            
        return resultado
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
            
        # Calcular o valor exato da fatura atual dinamicamente
        from datetime import datetime
        import pytz
        fuso = pytz.timezone("America/Sao_Paulo")
        hoje = datetime.now(fuso)
        
        gastos = db.query(GastoDiario).filter(
            GastoDiario.cartao_id == cartao.id,
            GastoDiario.tipo_pagamento.ilike('credito'),
            GastoDiario.pago == False
        ).all()
        
        valor_fatura = 0.0
        dia_fechamento = cartao.data_fatura if cartao.data_fatura else 15
        
        gastos_para_pagar = []
        for g in gastos:
            d = g.data
            mes_fatura = d.month - 1
            ano_fatura = d.year
            
            if d.day > dia_fechamento:
                mes_fatura += 1
                if mes_fatura > 11:
                    mes_fatura = 0
                    ano_fatura += 1
                    
            if mes_fatura == (hoje.month - 1) and ano_fatura == hoje.year:
                valor_fatura += g.valor
                gastos_para_pagar.append(g)
        
        # 1. Abate do saldo a fatura total calculada
        cartao.saldo -= valor_fatura
        # 2. Devolve o limite para o cartão
        cartao.limite += valor_fatura
        
        # 3. Marca esses gastos específicos como PAGOS para saírem da próxima conta
        for gp in gastos_para_pagar:
            gp.pago = True
            
        cartao.fatura_atual = 0 # Pode deixar zerado na tabela original, o dinâmico resolve
        
        db.commit()
        db.refresh(cartao)
        
        # Convertemos para dict para retornar
        return {
            "mensagem": "Fatura paga com sucesso!",
            "valor_pago": round(valor_fatura, 2),
            "novo_saldo": round(cartao.saldo, 2),
            "novo_limite": round(cartao.limite, 2)
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Erro ao pagar fatura: {str(e)}')