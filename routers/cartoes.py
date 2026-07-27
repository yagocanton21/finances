from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
import pytz
from database import get_db
from models import Cartao, GastoDiario
from schemas import CartaoBase

router = APIRouter()


def _calcular_fatura_do_mes(gastos: list, dia_fechamento: int, mes_ref: int, ano_ref: int) -> float:
    """
    Calcula o valor da fatura de um cartão para um mês/ano de referência.
    Centraliza a lógica de fechamento para evitar duplicação entre listar_cartoes e pagar_fatura.
    """
    total = 0.0
    for g in gastos:
        d = g.data
        mes_fatura = d.month - 1
        ano_fatura = d.year

        if d.day > dia_fechamento:
            mes_fatura += 1
            if mes_fatura > 11:
                mes_fatura = 0
                ano_fatura += 1

        if mes_fatura == (mes_ref - 1) and ano_fatura == ano_ref:
            total += g.valor

    return round(total, 2)


@router.post('/')
def criar_cartao(cartao_in: CartaoBase, db: Session = Depends(get_db)):
    try:
        db_cartao = Cartao(**cartao_in.model_dump())
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

        if not cartoes:
            return []

        # Busca TODOS os gastos de crédito não pagos de todos os cartões em UMA ÚNICA query
        # (elimina o N+1: antes era 1 query por cartão)
        ids_cartoes = [c.id for c in cartoes]
        todos_gastos = db.query(GastoDiario).filter(
            GastoDiario.cartao_id.in_(ids_cartoes),
            GastoDiario.tipo_pagamento == 'credito',
            GastoDiario.pago == False
        ).all()

        # Agrupa os gastos por cartao_id em memória
        gastos_por_cartao: dict[int, list] = {c.id: [] for c in cartoes}
        for g in todos_gastos:
            gastos_por_cartao[g.cartao_id].append(g)

        resultado = []
        for c in cartoes:
            cartao_dict = {
                col.name: getattr(c, col.name)
                for col in c.__table__.columns
            }
            dia_fechamento = c.data_fatura if c.data_fatura else 15
            cartao_dict['fatura_atual'] = _calcular_fatura_do_mes(
                gastos_por_cartao[c.id],
                dia_fechamento,
                hoje.month,
                hoje.year,
            )
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

        fuso = pytz.timezone("America/Sao_Paulo")
        hoje = datetime.now(fuso)

        gastos = db.query(GastoDiario).filter(
            GastoDiario.cartao_id == cartao.id,
            GastoDiario.tipo_pagamento.ilike('credito'),
            GastoDiario.pago == False
        ).all()

        dia_fechamento = cartao.data_fatura if cartao.data_fatura else 15

        # Identifica os gastos que pertencem à fatura do mês atual
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
                gastos_para_pagar.append(g)

        valor_fatura = round(sum(g.valor for g in gastos_para_pagar), 2)

        # 1. Abate do saldo a fatura total calculada
        cartao.saldo -= valor_fatura
        # 2. Devolve o limite para o cartão
        cartao.limite += valor_fatura
        # 3. Marca esses gastos específicos como PAGOS
        for gp in gastos_para_pagar:
            gp.pago = True

        cartao.fatura_atual = 0

        db.commit()
        db.refresh(cartao)

        return {
            "mensagem": "Fatura paga com sucesso!",
            "valor_pago": valor_fatura,
            "novo_saldo": round(cartao.saldo, 2),
            "novo_limite": round(cartao.limite, 2)
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Erro ao pagar fatura: {str(e)}')