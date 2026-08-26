import calendar
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app_logging import log_internal_error
from database import get_db
from models import (
    AporteReserva,
    Categoria,
    ExecucaoRecorrencia,
    MetaReserva,
    OrcamentoCategoria,
    Recorrencia,
)
from routers.gastos_diarios import criar_gasto_diario
from routers.receitas import criar_receita
from schemas.gastos_diarios import GastoDiarioBase
from schemas.planejamento import MetaReservaIn, MovimentoMetaIn, OrcamentoIn, RecorrenciaIn
from schemas.receitas import ReceitaBase
from services.contas import creditar, resolver_conta

router = APIRouter()


def _proximo_mes(data_atual: date, dia_mes: int) -> date:
    mes = data_atual.month + 1
    ano = data_atual.year
    if mes == 13:
        mes = 1
        ano += 1
    dia = min(dia_mes, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


@router.post("/recorrencias")
def criar_recorrencia(entrada: RecorrenciaIn, db: Session = Depends(get_db)):
    recorrencia = Recorrencia(**entrada.model_dump(mode="python"))
    db.add(recorrencia)
    db.commit()
    db.refresh(recorrencia)
    return recorrencia


@router.get("/recorrencias")
def listar_recorrencias(db: Session = Depends(get_db)):
    return db.query(Recorrencia).order_by(Recorrencia.proxima_data, Recorrencia.id).all()


@router.post("/recorrencias/processar")
def processar_recorrencias(
    ate: date = Query(default_factory=date.today), db: Session = Depends(get_db)
):
    processadas = []
    recorrencias = (
        db.query(Recorrencia)
        .filter(Recorrencia.ativa.is_(True), Recorrencia.proxima_data <= ate)
        .order_by(Recorrencia.proxima_data, Recorrencia.id)
        .all()
    )
    for recorrencia in recorrencias:
        ciclos = 0
        while recorrencia.proxima_data <= ate and ciclos < 120:
            prevista = recorrencia.proxima_data
            existente = db.query(ExecucaoRecorrencia).filter(
                ExecucaoRecorrencia.recorrencia_id == recorrencia.id,
                ExecucaoRecorrencia.data_prevista == prevista,
            ).first()
            if not existente:
                instante = datetime.combine(prevista, time(hour=12))
                if recorrencia.tipo_lancamento == "receita":
                    entidade = criar_receita(
                        ReceitaBase(
                            descricao=recorrencia.descricao,
                            valor=recorrencia.valor,
                            data=instante,
                            categoria_id=recorrencia.categoria_id,
                            conta_id=recorrencia.conta_id,
                        ),
                        db,
                    )
                    tipo_entidade = "receita"
                else:
                    entidade = criar_gasto_diario(
                        GastoDiarioBase(
                            descricao=recorrencia.descricao,
                            valor=recorrencia.valor,
                            data=instante,
                            categoria_id=recorrencia.categoria_id,
                            conta_id=recorrencia.conta_id,
                            cartao_id=recorrencia.cartao_id,
                            tipo_pagamento=recorrencia.tipo_pagamento,
                            parcelas=recorrencia.parcelas,
                        ),
                        db,
                    )
                    tipo_entidade = "gasto"
                execucao = ExecucaoRecorrencia(
                    recorrencia_id=recorrencia.id,
                    data_prevista=prevista,
                    entidade=tipo_entidade,
                    entidade_id=entidade.id,
                )
                db.add(execucao)
                processadas.append(
                    {"recorrencia_id": recorrencia.id, "data": prevista, "entidade_id": entidade.id}
                )
            recorrencia.proxima_data = _proximo_mes(prevista, recorrencia.dia_mes)
            db.commit()
            ciclos += 1
    return {"processadas": processadas, "total": len(processadas)}


@router.post("/orcamentos")
def salvar_orcamento(entrada: OrcamentoIn, db: Session = Depends(get_db)):
    categoria = db.query(Categoria).filter(Categoria.id == entrada.categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada")
    orcamento = db.query(OrcamentoCategoria).filter(
        OrcamentoCategoria.categoria_id == entrada.categoria_id,
        OrcamentoCategoria.dono == entrada.dono,
        OrcamentoCategoria.mes == entrada.mes,
        OrcamentoCategoria.ano == entrada.ano,
    ).first()
    if not orcamento:
        orcamento = OrcamentoCategoria(**entrada.model_dump())
        db.add(orcamento)
    else:
        orcamento.limite = entrada.limite
        orcamento.alerta_percentual = entrada.alerta_percentual
    db.commit()
    db.refresh(orcamento)
    return orcamento


@router.get("/orcamentos")
def listar_orcamentos(
    mes: int = Query(..., ge=1, le=12),
    ano: int = Query(..., ge=1900, le=2200),
    dono: str = Query(default="Eu", min_length=1),
    db: Session = Depends(get_db),
):
    return db.query(OrcamentoCategoria).filter(
        OrcamentoCategoria.mes == mes,
        OrcamentoCategoria.ano == ano,
        OrcamentoCategoria.dono == dono,
    ).all()


@router.post("/metas")
def criar_meta(entrada: MetaReservaIn, db: Session = Depends(get_db)):
    meta = MetaReserva(**entrada.model_dump())
    db.add(meta)
    db.commit()
    db.refresh(meta)
    return meta


@router.get("/metas")
def listar_metas(
    dono: str = Query(default="Eu", min_length=1), db: Session = Depends(get_db)
):
    metas = db.query(MetaReserva).filter(
        MetaReserva.dono == dono, MetaReserva.ativa.is_(True)
    ).order_by(MetaReserva.prazo, MetaReserva.id).all()
    return [
        {
            "id": meta.id,
            "nome": meta.nome,
            "valor_alvo": meta.valor_alvo,
            "saldo": meta.saldo,
            "prazo": meta.prazo,
            "progresso_percentual": (
                min((meta.saldo / meta.valor_alvo) * 100, 100) if meta.valor_alvo else 0
            ),
        }
        for meta in metas
    ]


@router.post("/metas/{meta_id}/retiradas")
def retirar_da_meta(
    meta_id: int, entrada: MovimentoMetaIn, db: Session = Depends(get_db)
):
    try:
        meta = (
            db.query(MetaReserva)
            .filter(MetaReserva.id == meta_id, MetaReserva.ativa.is_(True))
            .with_for_update()
            .first()
        )
        if not meta:
            raise HTTPException(status_code=404, detail="Meta nao encontrada")
        if meta.saldo < entrada.valor:
            raise HTTPException(status_code=409, detail="Saldo insuficiente na meta")
        conta = resolver_conta(db, conta_id=entrada.conta_id)
        meta.saldo -= entrada.valor
        creditar(db, conta, entrada.valor)
        movimento = AporteReserva(
            descricao=entrada.descricao,
            valor=entrada.valor,
            data=datetime.combine(entrada.data, time(hour=12)),
            conta_id=conta.id,
            meta_id=meta.id,
            tipo="retirada",
        )
        db.add(movimento)
        db.commit()
        return movimento
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("retirar_da_meta")
        raise HTTPException(status_code=500, detail="Erro ao retirar da meta")
