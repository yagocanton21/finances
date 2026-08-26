import os
import secrets
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Optional
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import extract, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app_logging import log_internal_error
from database import get_db
import pytz

from models import AuditoriaAgente, Cartao, Categoria, Compra, Conta, Fatura, GastoDiario, Receita
from schemas.agente import LancamentoAgenteIn, PagamentoFaturaAgenteIn, TipoLancamento
from schemas.gastos_diarios import TipoPagamento
from services.contas import creditar, debitar, garantir_conta_cartao
from services.faturas import (
    processar_pagamento_fatura,
    referencia_fatura_atual,
    sincronizar_fatura,
)

router = APIRouter()
CENTAVOS = Decimal("0.01")


def _normalizar_requisicao(entrada: LancamentoAgenteIn) -> dict:
    """Payload financeiro usado para validar a reutilizacao da chave idempotente."""
    return jsonable_encoder(entrada.model_dump(exclude={"external_id"}))


def _mesma_requisicao(requisicao_salva: dict, entrada: LancamentoAgenteIn) -> bool:
    # Auditorias criadas antes desta validacao guardavam external_id no payload.
    salva = dict(requisicao_salva)
    salva.pop("external_id", None)
    return salva == _normalizar_requisicao(entrada)


def _mesmo_pagamento(requisicao_salva: dict, entrada: PagamentoFaturaAgenteIn) -> bool:
    salva = dict(requisicao_salva)
    salva.pop("external_id", None)
    atual = jsonable_encoder(entrada.model_dump(exclude={"external_id"}))
    return salva == atual


def autenticar_agente(
    x_agent_token: Annotated[Optional[str], Header()] = None,
) -> str:
    token_esperado = os.getenv("HERMES_API_TOKEN")
    if not token_esperado:
        raise HTTPException(status_code=503, detail="Integracao Hermes nao configurada")
    if not x_agent_token or not secrets.compare_digest(x_agent_token, token_esperado):
        raise HTTPException(status_code=401, detail="Token do agente invalido")
    return "hermes"


def _resolver_conta(
    db: Session,
    *,
    conta_id: Optional[int],
    conta: Optional[str],
    bloquear=False,
) -> Cartao:
    query = db.query(Cartao).filter(Cartao.ativo.is_(True))
    if conta_id:
        query = query.filter(Cartao.id == conta_id)
    else:
        query = query.filter(func.lower(Cartao.nome) == conta.strip().lower())
    if bloquear:
        query = query.with_for_update()
    cartoes = query.all()
    if not cartoes:
        raise HTTPException(status_code=422, detail="Conta ativa nao encontrada")
    if len(cartoes) > 1:
        raise HTTPException(
            status_code=409,
            detail={"mensagem": "Nome de conta ambiguo", "conta_ids": [c.id for c in cartoes]},
        )
    return cartoes[0]


def _resolver_cartao(db: Session, entrada: LancamentoAgenteIn, bloquear=False) -> Cartao:
    return _resolver_conta(
        db,
        conta_id=entrada.conta_id,
        conta=entrada.conta,
        bloquear=bloquear,
    )


def _resolver_categoria(db: Session, entrada: LancamentoAgenteIn) -> Optional[Categoria]:
    if entrada.categoria_id:
        categoria = db.query(Categoria).filter(Categoria.id == entrada.categoria_id).first()
        if not categoria:
            raise HTTPException(status_code=422, detail="Categoria nao encontrada")
        return categoria
    if entrada.categoria:
        categorias = db.query(Categoria).filter(
            func.lower(Categoria.nome) == entrada.categoria.strip().lower()
        ).all()
        if not categorias:
            raise HTTPException(status_code=422, detail="Categoria nao encontrada")
        if len(categorias) > 1:
            raise HTTPException(status_code=409, detail="Nome de categoria ambiguo")
        return categorias[0]
    return None


def _validar_fundos(cartao: Cartao, entrada: LancamentoAgenteIn) -> None:
    if entrada.tipo_lancamento != TipoLancamento.gasto:
        return
    if entrada.tipo_pagamento in (TipoPagamento.debito, TipoPagamento.pix):
        if cartao.saldo < entrada.valor:
            raise HTTPException(status_code=409, detail="Saldo insuficiente")
    elif cartao.limite < entrada.valor:
        raise HTTPException(status_code=409, detail="Limite insuficiente")


def _aplicar_fundos(cartao: Cartao, entrada: LancamentoAgenteIn) -> None:
    """Compatibilidade para testes e objetos legados sem sessao de banco."""
    if entrada.tipo_lancamento == TipoLancamento.receita:
        cartao.saldo += entrada.valor
    elif entrada.tipo_pagamento in (TipoPagamento.debito, TipoPagamento.pix):
        cartao.saldo -= entrada.valor
    else:
        cartao.limite -= entrada.valor


@router.get("/contas", dependencies=[Depends(autenticar_agente)])
def listar_contas(db: Session = Depends(get_db)):
    return [
        {
            "id": c.id,
            "cartao_id": c.id,
            "conta_pagamento_id": c.conta_padrao_id,
            "nome": c.nome,
            "dono": c.dono,
            "saldo": c.conta_padrao.saldo if c.conta_padrao else c.saldo,
            "limite": c.limite,
            "limite_total": c.limite_total,
        }
        for c in db.query(Cartao).filter(Cartao.ativo.is_(True)).order_by(Cartao.nome).all()
    ]


@router.get("/contas-bancarias", dependencies=[Depends(autenticar_agente)])
def listar_contas_bancarias(db: Session = Depends(get_db)):
    return [
        {"id": conta.id, "nome": conta.nome, "dono": conta.dono, "saldo": conta.saldo}
        for conta in db.query(Conta).filter(Conta.ativa.is_(True)).order_by(Conta.nome).all()
    ]


@router.get("/categorias", dependencies=[Depends(autenticar_agente)])
def listar_categorias(db: Session = Depends(get_db)):
    return [
        {"id": c.id, "nome": c.nome}
        for c in db.query(Categoria).order_by(Categoria.nome).all()
    ]


@router.get("/resumo", dependencies=[Depends(autenticar_agente)])
def resumo_mensal(
    mes: int = Query(..., ge=1, le=12),
    ano: int = Query(..., ge=1900, le=2200),
    db: Session = Depends(get_db),
):
    receitas = db.query(func.sum(Receita.valor)).filter(
        extract("month", Receita.data) == mes,
        extract("year", Receita.data) == ano,
    ).scalar() or Decimal("0")
    gastos = db.query(func.sum(GastoDiario.valor)).filter(
        extract("month", GastoDiario.data) == mes,
        extract("year", GastoDiario.data) == ano,
    ).scalar() or Decimal("0")
    return {
        "mes": mes,
        "ano": ano,
        "total_receitas": receitas,
        "total_gastos": gastos,
        "saldo_do_periodo": receitas - gastos,
    }


@router.post("/lancamentos/preview", dependencies=[Depends(autenticar_agente)])
def prever_lancamento(entrada: LancamentoAgenteIn, db: Session = Depends(get_db)):
    cartao = _resolver_cartao(db, entrada)
    categoria = _resolver_categoria(db, entrada)
    _validar_fundos(cartao, entrada)
    return {
        "valido": True,
        "precisa_confirmacao": True,
        "resumo": {
            "tipo_lancamento": entrada.tipo_lancamento,
            "descricao": entrada.descricao,
            "valor": entrada.valor,
            "data": entrada.data,
            "conta": {"id": cartao.id, "nome": cartao.nome},
            "categoria": ({"id": categoria.id, "nome": categoria.nome} if categoria else None),
            "tipo_pagamento": entrada.tipo_pagamento,
            "parcelas": entrada.parcelas,
        },
    }


@router.post("/lancamentos")
def registrar_lancamento(
    entrada: LancamentoAgenteIn,
    agente: str = Depends(autenticar_agente),
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
    db: Session = Depends(get_db),
):
    external_id = idempotency_key or entrada.external_id
    if not external_id:
        raise HTTPException(status_code=422, detail="Idempotency-Key ou external_id e obrigatorio")
    if len(external_id) > 120:
        raise HTTPException(status_code=422, detail="Chave de idempotencia excede 120 caracteres")

    existente = db.query(AuditoriaAgente).filter(
        AuditoriaAgente.external_id == external_id
    ).first()
    if existente:
        if not _mesma_requisicao(existente.requisicao, entrada):
            raise HTTPException(
                status_code=409,
                detail="Chave de idempotencia ja utilizada com outro lancamento",
            )
        return {**existente.resposta, "idempotente": True}

    try:
        cartao = _resolver_cartao(db, entrada, bloquear=True)
        conta = garantir_conta_cartao(db, cartao)
        categoria = _resolver_categoria(db, entrada)
        _validar_fundos(cartao, entrada)
        if entrada.tipo_lancamento == TipoLancamento.receita:
            creditar(db, conta, entrada.valor)
        elif entrada.tipo_pagamento in (TipoPagamento.debito, TipoPagamento.pix):
            debitar(db, conta, entrada.valor)
        else:
            cartao.limite -= entrada.valor

        ids = []
        entidade = entrada.tipo_lancamento.value
        if entrada.tipo_lancamento == TipoLancamento.receita:
            receita = Receita(
                descricao=entrada.descricao,
                valor=entrada.valor,
                data=entrada.data,
                cartao_id=cartao.id,
                conta_id=conta.id,
                categoria_id=categoria.id if categoria else None,
                origem=agente,
                external_id=external_id,
            )
            db.add(receita)
            db.flush()
            ids.append(receita.id)
        else:
            compra_id = str(uuid4())
            compra = Compra(
                id=compra_id,
                descricao=entrada.descricao,
                valor_total=entrada.valor,
                data_compra=entrada.data,
                parcelas=entrada.parcelas,
                tipo_pagamento=entrada.tipo_pagamento.value,
                cartao_id=cartao.id if entrada.tipo_pagamento == TipoPagamento.credito else None,
                conta_id=conta.id,
                categoria_id=categoria.id if categoria else None,
                situacao="ativa",
            )
            db.add(compra)
            valor_parcela = (entrada.valor / entrada.parcelas).quantize(
                CENTAVOS, rounding=ROUND_HALF_UP
            )
            valor_ultima = entrada.valor - valor_parcela * (entrada.parcelas - 1)
            for indice in range(entrada.parcelas):
                numero = indice + 1
                gasto = GastoDiario(
                    descricao=(
                        f"{entrada.descricao} ({numero}/{entrada.parcelas})"
                        if entrada.parcelas > 1 else entrada.descricao
                    ),
                    valor=valor_ultima if numero == entrada.parcelas else valor_parcela,
                    data=entrada.data + relativedelta(months=indice),
                    tipo_pagamento=entrada.tipo_pagamento.value,
                    parcelas=entrada.parcelas,
                    compra_id=compra_id,
                    numero_parcela=numero,
                    categoria_id=categoria.id if categoria else None,
                    cartao_id=cartao.id,
                    conta_id=conta.id,
                    pago=False,
                    origem=agente,
                    external_id=external_id,
                )
                db.add(gasto)
                db.flush()
                ids.append(gasto.id)

        resposta = {
            "status": "registrado",
            "tipo_lancamento": entidade,
            "lancamento_ids": ids,
            "external_id": external_id,
            "conta": {"id": cartao.id, "nome": cartao.nome},
            "saldo_resultante": cartao.saldo,
            "limite_resultante": cartao.limite,
            "idempotente": False,
        }
        auditoria = AuditoriaAgente(
            external_id=external_id,
            agente=agente,
            acao="registrar_lancamento",
            entidade=entidade,
            entidade_id=ids[0],
            status="registrado",
            requisicao=_normalizar_requisicao(entrada),
            resposta=jsonable_encoder(resposta),
        )
        db.add(auditoria)
        db.commit()
        return resposta
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        existente = db.query(AuditoriaAgente).filter(
            AuditoriaAgente.external_id == external_id
        ).first()
        if existente:
            if not _mesma_requisicao(existente.requisicao, entrada):
                raise HTTPException(
                    status_code=409,
                    detail="Chave de idempotencia ja utilizada com outro lancamento",
                )
            return {**existente.resposta, "idempotente": True}
        raise HTTPException(status_code=409, detail="Chave de idempotencia em conflito")
    except Exception:
        db.rollback()
        log_internal_error("registrar_lancamento_agente")
        raise HTTPException(status_code=500, detail="Erro ao registrar lancamento do agente")


@router.get("/lancamentos/{external_id}", dependencies=[Depends(autenticar_agente)])
def consultar_lancamento(external_id: str, db: Session = Depends(get_db)):
    auditoria = db.query(AuditoriaAgente).filter(
        AuditoriaAgente.external_id == external_id
    ).first()
    if not auditoria:
        raise HTTPException(status_code=404, detail="Lancamento do agente nao encontrado")
    return {
        "external_id": auditoria.external_id,
        "agente": auditoria.agente,
        "status": auditoria.status,
        "criado_em": auditoria.criado_em,
        "resposta": auditoria.resposta,
    }


def _resumo_pagamento_agente(
    db: Session, cartao: Cartao, mes_ref: int, ano_ref: int
):
    fatura, gastos_da_fatura = sincronizar_fatura(
        db, cartao, mes_ref, ano_ref, criar=False
    )
    total_lancado = sum((gasto.valor for gasto in gastos_da_fatura), Decimal("0"))
    total = max(fatura.total if fatura else Decimal("0"), total_lancado)
    total_pago = (
        sum(
            (item.valor for item in fatura.pagamentos if item.estornado_em is None),
            Decimal("0"),
        )
        if fatura
        else Decimal("0")
    )
    return {
        "cartao_id": cartao.id,
        "cartao": cartao.nome,
        "mes_ref": mes_ref,
        "ano_ref": ano_ref,
        "total": total,
        "total_pago": total_pago,
        "saldo_restante": max(total - total_pago, Decimal("0")),
        "situacao": fatura.situacao if fatura else ("aberta" if total else "sem_lancamentos"),
    }


@router.post("/pagamentos/fatura/preview", dependencies=[Depends(autenticar_agente)])
def prever_pagamento_fatura(
    entrada: PagamentoFaturaAgenteIn, db: Session = Depends(get_db)
):
    hoje = datetime.now(pytz.timezone("America/Sao_Paulo"))
    cartao = _resolver_conta(
        db, conta_id=entrada.conta_id, conta=entrada.conta, bloquear=False
    )
    mes_padrao, ano_padrao = referencia_fatura_atual(hoje, cartao.data_fatura)
    resumo = _resumo_pagamento_agente(
        db, cartao, entrada.mes_ref or mes_padrao, entrada.ano_ref or ano_padrao
    )
    if resumo["saldo_restante"] <= 0:
        raise HTTPException(status_code=409, detail="Nao ha fatura em aberto")
    valor = entrada.valor or resumo["saldo_restante"]
    if valor > resumo["saldo_restante"]:
        raise HTTPException(status_code=409, detail="Valor excede o saldo restante da fatura")
    return {
        "valido": True,
        "precisa_confirmacao": True,
        "operacao": "pagar_fatura",
        "resumo": {**resumo, "valor": valor, "movimentara_saldo": True},
    }


def _registrar_pagamento_agente(
    entrada: PagamentoFaturaAgenteIn,
    *,
    agente: str,
    idempotency_key: Optional[str],
    db: Session,
    movimentar_saldo: bool,
    origem: str,
):
    external_id = idempotency_key or entrada.external_id
    if not external_id:
        raise HTTPException(status_code=422, detail="Idempotency-Key ou external_id e obrigatorio")
    existente = db.query(AuditoriaAgente).filter(
        AuditoriaAgente.external_id == external_id
    ).first()
    if existente:
        if not _mesmo_pagamento(existente.requisicao, entrada):
            raise HTTPException(
                status_code=409,
                detail="Chave de idempotencia utilizada com outro pagamento",
            )
        return {**existente.resposta, "idempotente": True}
    if not entrada.confirmado:
        raise HTTPException(
            status_code=409,
            detail="Confirmacao obrigatoria; execute o preview antes de registrar",
        )

    hoje = datetime.now(pytz.timezone("America/Sao_Paulo"))
    cartao = _resolver_conta(
        db, conta_id=entrada.conta_id, conta=entrada.conta, bloquear=False
    )
    mes_padrao, ano_padrao = referencia_fatura_atual(hoje, cartao.data_fatura)
    mes_ref = entrada.mes_ref or mes_padrao
    ano_ref = entrada.ano_ref or ano_padrao
    resposta = processar_pagamento_fatura(
        db,
        cartao_id=cartao.id,
        mes_ref=mes_ref,
        ano_ref=ano_ref,
        valor=entrada.valor,
        idempotency_key=external_id,
        origem=origem,
        movimentar_saldo=movimentar_saldo,
        restaurar_limite=True,
        conta_id=entrada.conta_pagamento_id,
        agora=hoje,
    )
    resposta.update({"agente": agente, "external_id": external_id})
    auditoria = AuditoriaAgente(
        external_id=external_id,
        agente=agente,
        acao="pagar_fatura" if movimentar_saldo else "reconciliar_pagamento_fatura",
        entidade="fatura",
        entidade_id=resposta["fatura_id"],
        status="registrado",
        requisicao=jsonable_encoder(entrada.model_dump(exclude={"external_id"})),
        resposta=jsonable_encoder(resposta),
    )
    db.add(auditoria)
    db.commit()
    return resposta


@router.post("/pagamentos/fatura")
def pagar_fatura_pelo_agente(
    entrada: PagamentoFaturaAgenteIn,
    agente: str = Depends(autenticar_agente),
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
    db: Session = Depends(get_db),
):
    try:
        return _registrar_pagamento_agente(
            entrada,
            agente=agente,
            idempotency_key=idempotency_key,
            db=db,
            movimentar_saldo=True,
            origem="hermes",
        )
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Chave de idempotencia em conflito")


@router.post("/pagamentos/fatura/reconciliar")
def reconciliar_pagamento_fatura_pelo_agente(
    entrada: PagamentoFaturaAgenteIn,
    agente: str = Depends(autenticar_agente),
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
    db: Session = Depends(get_db),
):
    """Registra pagamento externo, preserva o saldo e restaura o limite do cartão."""
    try:
        return _registrar_pagamento_agente(
            entrada,
            agente=agente,
            idempotency_key=idempotency_key,
            db=db,
            movimentar_saldo=False,
            origem="hermes_externo",
        )
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Chave de idempotencia em conflito")


@router.delete("/lancamentos/{external_id}")
def estornar_lancamento(
    external_id: str,
    agente: str = Depends(autenticar_agente),
    db: Session = Depends(get_db),
):
    try:
        auditoria = db.query(AuditoriaAgente).filter(
            AuditoriaAgente.external_id == external_id
        ).with_for_update().first()
        if not auditoria:
            raise HTTPException(status_code=404, detail="Lancamento do agente nao encontrado")
        if auditoria.status == "estornado":
            return {**auditoria.resposta, "idempotente": True}

        if auditoria.entidade == TipoLancamento.gasto.value:
            gastos = db.query(GastoDiario).filter(
                GastoDiario.external_id == external_id
            ).with_for_update().all()
            if not gastos:
                raise HTTPException(status_code=409, detail="Gastos vinculados nao encontrados")
            if any(gasto.pago for gasto in gastos):
                raise HTTPException(status_code=409, detail="Fatura paga; estorne a fatura primeiro")
            cartao = db.query(Cartao).filter(
                Cartao.id == gastos[0].cartao_id
            ).with_for_update().first()
            conta = garantir_conta_cartao(db, cartao)
            total = sum((g.valor for g in gastos), Decimal("0"))
            if gastos[0].tipo_pagamento in (TipoPagamento.debito.value, TipoPagamento.pix.value):
                creditar(db, conta, total)
            else:
                cartao.limite += total
            for gasto in gastos:
                db.delete(gasto)
        else:
            receita = db.query(Receita).filter(
                Receita.external_id == external_id
            ).with_for_update().first()
            if not receita:
                raise HTTPException(status_code=409, detail="Receita vinculada nao encontrada")
            cartao = db.query(Cartao).filter(
                Cartao.id == receita.cartao_id
            ).with_for_update().first()
            conta = garantir_conta_cartao(db, cartao)
            if conta.saldo < receita.valor:
                raise HTTPException(status_code=409, detail="Saldo insuficiente para estornar receita")
            debitar(db, conta, receita.valor)
            db.delete(receita)

        resposta = {
            "status": "estornado",
            "external_id": external_id,
            "agente": agente,
            "idempotente": False,
        }
        auditoria.status = "estornado"
        auditoria.acao = "estornar_lancamento"
        auditoria.resposta = resposta
        db.commit()
        return resposta
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("estornar_lancamento_agente")
        raise HTTPException(status_code=500, detail="Erro ao estornar lancamento do agente")
