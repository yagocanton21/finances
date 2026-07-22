from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import GastoDiario, Cartao
from schemas import GastoDiarioBase
from datetime import timedelta

router = APIRouter()

@router.post('/')
def criar_gasto_diario(gasto_in: GastoDiarioBase, db: Session = Depends(get_db)):
    try:
        dados_gasto = gasto_in.dict() if hasattr(gasto_in, 'dict') else gasto_in.model_dump()
        db_gasto = GastoDiario(**dados_gasto)
       
        cartao = db.query(Cartao).filter(Cartao.id == db_gasto.cartao_id).first()
        if not cartao:
            raise HTTPException(status_code=404, detail='Cartão não encontrado')

        if db_gasto.tipo_pagamento.lower() == 'debito' or db_gasto.tipo_pagamento.lower() == 'pix':
            cartao.saldo -= db_gasto.valor
            db_gasto.parcelas = 1
            db.add(db_gasto)
            db.commit()
            db.refresh(db_gasto)
            return db_gasto
            
        elif db_gasto.tipo_pagamento.lower() == 'credito':
            if gasto_in.parcelas <= 1:
                cartao.fatura_atual += db_gasto.valor
                cartao.limite -= db_gasto.valor
                db.add(db_gasto)
                db.commit()
                db.refresh(db_gasto)
                return db_gasto
            else:
                
                # Subtrai o valor TOTAL do limite
                cartao.limite -= db_gasto.valor
                
                # Valor exato da parcela (ex: 1000 / 10 = 100)
                valor_parcela = int(db_gasto.valor / gasto_in.parcelas)
                
                # Apenas a parcela 1 entra na fatura desse mês
                cartao.fatura_atual += valor_parcela
                
                primeiro_gasto = None
                for i in range(gasto_in.parcelas):
                    novo_gasto = GastoDiario(
                        descricao=f"{db_gasto.descricao} ({i+1}/{gasto_in.parcelas})",
                        valor=valor_parcela,
                        data=db_gasto.data + timedelta(days=30 * i), # Joga 1 mês pra frente
                        tipo_pagamento="credito",
                        parcelas=gasto_in.parcelas,
                        categoria_id=db_gasto.categoria_id,
                        cartao_id=db_gasto.cartao_id
                    )
                    db.add(novo_gasto)
                    if i == 0:
                        primeiro_gasto = novo_gasto
                        
                db.commit()
                db.refresh(primeiro_gasto)
                return primeiro_gasto
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Erro ao criar gasto diário: {str(e)}')

@router.get('/')
def listar_gastos_diarios(db: Session = Depends(get_db)):
    try:
        return db.query(GastoDiario).all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Erro ao listar gastos diários: {str(e)}')

@router.get('/{id}')
def buscar_gasto_diario(id: int, db: Session = Depends(get_db)):
    try:
        db_gasto = db.query(GastoDiario).filter(GastoDiario.id == id).first()
        if not db_gasto:
            raise HTTPException(status_code=404, detail='Gasto diário não encontrado')
        return db_gasto
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Erro ao buscar gasto diário: {str(e)}')

@router.put('/{id}')
def atualizar_gasto_diario(id: int, gasto_in: GastoDiarioBase, db: Session = Depends(get_db)):
    try:
        # Busca o gasto antigo no banco
        db_gasto = db.query(GastoDiario).filter(GastoDiario.id == id).first()
        if not db_gasto:
            raise HTTPException(status_code=404, detail='Gasto diário não encontrado')
            
        
        # Estorno do Gasto Antigo
        cartao_antigo = db.query(Cartao).filter(Cartao.id == db_gasto.cartao_id).first()
        if cartao_antigo:
            if db_gasto.tipo_pagamento.lower() == 'debito' or db_gasto.tipo_pagamento.lower() == 'pix':
                cartao_antigo.saldo += db_gasto.valor
            elif db_gasto.tipo_pagamento.lower() == 'credito':
                cartao_antigo.fatura_atual -= db_gasto.valor
                cartao_antigo.limite += db_gasto.valor
                
        # Atualizar os dados do Gasto
        db_gasto.descricao = gasto_in.descricao
        db_gasto.valor = gasto_in.valor
        db_gasto.data = gasto_in.data
        db_gasto.categoria_id = gasto_in.categoria_id
        db_gasto.cartao_id = gasto_in.cartao_id
        db_gasto.tipo_pagamento = gasto_in.tipo_pagamento
        
        # Nova Cobrança
        cartao_novo = db.query(Cartao).filter(Cartao.id == db_gasto.cartao_id).first()
        if not cartao_novo:
            raise HTTPException(status_code=404, detail='Novo Cartão não encontrado')
            
        if db_gasto.tipo_pagamento.lower() == 'debito' or db_gasto.tipo_pagamento.lower() == 'pix':
            cartao_novo.saldo -= db_gasto.valor
        elif db_gasto.tipo_pagamento.lower() == 'credito':
            cartao_novo.fatura_atual += db_gasto.valor
            cartao_novo.limite -= db_gasto.valor
            
        # Salva tudo de uma vez
        db.commit()
        db.refresh(db_gasto)
        return db_gasto
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Erro ao atualizar gasto diário: {str(e)}')

# Deletar Gasto
@router.delete('/{id}')
def deletar_gasto_diario(id: int, db: Session = Depends(get_db)):
    try:
        db_gasto = db.query(GastoDiario).filter(GastoDiario.id == id).first()
        if not db_gasto:
            raise HTTPException(status_code=404, detail='Gasto diário não encontrado')
        
        # Estorno do Gasto
        cartao = db.query(Cartao).filter(Cartao.id == db_gasto.cartao_id).first()
        if not cartao:
            raise HTTPException(status_code=404, detail='Cartão não encontrado ao tentar deletar o gasto')

        if db_gasto.tipo_pagamento.lower() == 'debito' or db_gasto.tipo_pagamento.lower() == 'pix':
            cartao.saldo += db_gasto.valor
        elif db_gasto.tipo_pagamento.lower() == 'credito':
            cartao.fatura_atual -= db_gasto.valor
            cartao.limite += db_gasto.valor     
        
        db.delete(db_gasto)
        db.commit()
        return {'mensagem': 'Gasto diário deletado com sucesso'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Erro ao deletar gasto diário: {str(e)}')
