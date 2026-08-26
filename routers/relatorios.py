import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
import pytz
from sqlalchemy import extract, func, or_
from sqlalchemy.orm import Session

from database import get_db
from models import (
    AporteReserva,
    Cartao,
    Categoria,
    Conta,
    Fatura,
    GastoDiario,
    MetaReserva,
    OrcamentoCategoria,
    PagamentoFatura,
    Receita,
    Recorrencia,
)
from schemas.gastos_diarios import TipoPagamento
from services.faturas import referencia_fatura

router = APIRouter()


def _filtro_dono(dono: str | None):
    if not dono:
        return True
    return func.coalesce(Cartao.dono, Conta.dono) == dono


def _fim_mes(mes: int, ano: int) -> datetime:
    ultimo = calendar.monthrange(ano, mes)[1]
    return datetime(ano, mes, ultimo, 23, 59, 59)


def _faturas_abertas_calculadas(db: Session, dono: str):
    cartoes = db.query(Cartao).filter(Cartao.ativo.is_(True), Cartao.dono == dono).all()
    resultado = []
    for cartao in cartoes:
        totais: dict[tuple[int, int], Decimal] = {}
        gastos = db.query(GastoDiario).filter(
            GastoDiario.cartao_id == cartao.id,
            GastoDiario.tipo_pagamento == TipoPagamento.credito.value,
        ).all()
        for gasto in gastos:
            referencia = referencia_fatura(gasto.data, cartao.data_fatura)
            totais[referencia] = totais.get(referencia, Decimal("0")) + gasto.valor
        for (mes_ref, ano_ref), total in totais.items():
            fatura = db.query(Fatura).filter(
                Fatura.cartao_id == cartao.id,
                Fatura.mes_ref == mes_ref,
                Fatura.ano_ref == ano_ref,
            ).first()
            pago = (
                sum(
                    (item.valor for item in fatura.pagamentos if item.estornado_em is None),
                    Decimal("0"),
                )
                if fatura
                else Decimal("0")
            )
            restante = max(total - pago, Decimal("0"))
            if restante > 0:
                resultado.append((cartao, mes_ref, ano_ref, restante))
    return resultado


@router.get("/resumo_mensal")
def resumo_mensal(
    mes: int = Query(..., ge=1, le=12),
    ano: int = Query(..., ge=1900, le=2200),
    dono: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
):
    filtro = _filtro_dono(dono)
    receitas = (
        db.query(func.sum(Receita.valor))
        .outerjoin(Cartao, Receita.cartao_id == Cartao.id)
        .outerjoin(Conta, Receita.conta_id == Conta.id)
        .filter(
            extract("month", Receita.data) == mes,
            extract("year", Receita.data) == ano,
            filtro,
        )
        .scalar()
        or Decimal("0.00")
    )
    gastos_agrupados = (
        db.query(GastoDiario.tipo_pagamento, func.sum(GastoDiario.valor))
        .outerjoin(Cartao, GastoDiario.cartao_id == Cartao.id)
        .outerjoin(Conta, GastoDiario.conta_id == Conta.id)
        .filter(
            extract("month", GastoDiario.data) == mes,
            extract("year", GastoDiario.data) == ano,
            filtro,
        )
        .group_by(GastoDiario.tipo_pagamento)
        .all()
    )
    por_tipo = {tipo: valor for tipo, valor in gastos_agrupados}
    credito = por_tipo.get(TipoPagamento.credito.value, Decimal("0"))
    debito = por_tipo.get(TipoPagamento.debito.value, Decimal("0"))
    pix = por_tipo.get(TipoPagamento.pix.value, Decimal("0"))
    total_gastos = credito + debito + pix

    categorias = (
        db.query(func.coalesce(Categoria.nome, "Sem categoria"), func.sum(GastoDiario.valor))
        .outerjoin(Categoria, GastoDiario.categoria_id == Categoria.id)
        .outerjoin(Cartao, GastoDiario.cartao_id == Cartao.id)
        .outerjoin(Conta, GastoDiario.conta_id == Conta.id)
        .filter(
            extract("month", GastoDiario.data) == mes,
            extract("year", GastoDiario.data) == ano,
            filtro,
        )
        .group_by(func.coalesce(Categoria.nome, "Sem categoria"))
        .order_by(func.sum(GastoDiario.valor).desc())
        .all()
    )

    movimentos_reserva = (
        db.query(AporteReserva.tipo, func.sum(AporteReserva.valor))
        .outerjoin(Cartao, AporteReserva.cartao_id == Cartao.id)
        .outerjoin(Conta, AporteReserva.conta_id == Conta.id)
        .filter(
            extract("month", AporteReserva.data) == mes,
            extract("year", AporteReserva.data) == ano,
            filtro,
        )
        .group_by(AporteReserva.tipo)
        .all()
    )
    reserva = {tipo: valor for tipo, valor in movimentos_reserva}
    aportes = reserva.get("aporte", Decimal("0"))
    retiradas = reserva.get("retirada", Decimal("0"))

    pagamentos_fatura = (
        db.query(func.sum(PagamentoFatura.valor))
        .join(Cartao, PagamentoFatura.cartao_id == Cartao.id)
        .filter(
            extract("month", PagamentoFatura.data_pagamento) == mes,
            extract("year", PagamentoFatura.data_pagamento) == ano,
            PagamentoFatura.movimentou_saldo.is_(True),
            PagamentoFatura.estornado_em.is_(None),
            Cartao.dono == dono if dono else True,
        )
        .scalar()
        or Decimal("0")
    )
    comprometido_apos_periodo = (
        db.query(func.sum(GastoDiario.valor))
        .outerjoin(Cartao, GastoDiario.cartao_id == Cartao.id)
        .outerjoin(Conta, GastoDiario.conta_id == Conta.id)
        .filter(
            GastoDiario.tipo_pagamento == TipoPagamento.credito.value,
            GastoDiario.pago.is_(False),
            GastoDiario.data > _fim_mes(mes, ano),
            filtro,
        )
        .scalar()
        or Decimal("0")
    )
    saldo_disponivel = (
        db.query(func.sum(Conta.saldo))
        .filter(Conta.ativa.is_(True), Conta.dono == dono if dono else True)
        .scalar()
        or Decimal("0")
    )
    resultado_competencia = receitas - total_gastos
    resultado_caixa = receitas - debito - pix - pagamentos_fatura - aportes + retiradas
    return {
        "mes": mes,
        "ano": ano,
        "regime": {
            "competencia": resultado_competencia,
            "caixa": resultado_caixa,
        },
        "receitas": {"total": receitas},
        "despesas": {
            "credito": credito,
            "debito": debito,
            "pix": pix,
            "total": total_gastos,
        },
        "pagamentos_fatura": pagamentos_fatura,
        "saldo_final": resultado_competencia,
        "saldo_disponivel_atual": saldo_disponivel,
        "categorias": [{"nome": nome, "total": total} for nome, total in categorias],
        "guardado": aportes,
        "retirado_reserva": retiradas,
        "parcelas_futuras": comprometido_apos_periodo,
        "comprometido_apos_periodo": comprometido_apos_periodo,
    }


@router.get("/orcamentos/status")
def status_orcamentos(
    mes: int = Query(..., ge=1, le=12),
    ano: int = Query(..., ge=1900, le=2200),
    dono: str = Query(default="Eu", min_length=1),
    db: Session = Depends(get_db),
):
    orcamentos = db.query(OrcamentoCategoria).filter(
        OrcamentoCategoria.mes == mes,
        OrcamentoCategoria.ano == ano,
        OrcamentoCategoria.dono == dono,
    ).all()
    resultado = []
    for orcamento in orcamentos:
        gasto = (
            db.query(func.sum(GastoDiario.valor))
            .outerjoin(Cartao, GastoDiario.cartao_id == Cartao.id)
            .outerjoin(Conta, GastoDiario.conta_id == Conta.id)
            .filter(
                GastoDiario.categoria_id == orcamento.categoria_id,
                extract("month", GastoDiario.data) == mes,
                extract("year", GastoDiario.data) == ano,
                func.coalesce(Cartao.dono, Conta.dono) == dono,
            )
            .scalar()
            or Decimal("0")
        )
        percentual = (gasto / orcamento.limite * 100) if orcamento.limite else Decimal("0")
        resultado.append(
            {
                "id": orcamento.id,
                "categoria_id": orcamento.categoria_id,
                "limite": orcamento.limite,
                "gasto": gasto,
                "disponivel": orcamento.limite - gasto,
                "percentual": percentual,
                "situacao": (
                    "estourado"
                    if percentual >= 100
                    else "alerta"
                    if percentual >= orcamento.alerta_percentual
                    else "ok"
                ),
            }
        )
    return resultado


@router.get("/projecao")
def projetar_saldo(
    dias: int = Query(default=90, ge=1, le=365),
    dono: str = Query(default="Eu", min_length=1),
    db: Session = Depends(get_db),
):
    hoje = date.today()
    saldo = db.query(func.sum(Conta.saldo)).filter(
        Conta.ativa.is_(True), Conta.dono == dono
    ).scalar() or Decimal("0")
    eventos = []
    recorrencias = db.query(Recorrencia).filter(
        Recorrencia.ativa.is_(True), Recorrencia.proxima_data <= hoje + timedelta(days=dias)
    ).all()
    for recorrencia in recorrencias:
        if recorrencia.conta_id:
            conta = db.query(Conta).filter(Conta.id == recorrencia.conta_id).first()
            if not conta or conta.dono != dono:
                continue
        sinal = Decimal("1") if recorrencia.tipo_lancamento == "receita" else Decimal("-1")
        data_evento = recorrencia.proxima_data
        limite_projecao = hoje + timedelta(days=dias)
        while data_evento <= limite_projecao:
            eventos.append(
                {
                    "data": data_evento,
                    "descricao": recorrencia.descricao,
                    "valor": sinal * recorrencia.valor,
                    "tipo": "recorrencia",
                }
            )
            mes = data_evento.month + 1
            ano = data_evento.year
            if mes == 13:
                mes = 1
                ano += 1
            data_evento = date(
                ano,
                mes,
                min(recorrencia.dia_mes, calendar.monthrange(ano, mes)[1]),
            )
    for cartao, mes_ref, ano_ref, restante in _faturas_abertas_calculadas(db, dono):
        dia = min(cartao.dia_vencimento, calendar.monthrange(ano_ref, mes_ref)[1])
        vencimento = date(ano_ref, mes_ref, dia)
        if vencimento <= hoje + timedelta(days=dias):
            eventos.append(
                {
                    "data": vencimento,
                    "descricao": f"Fatura {cartao.nome}",
                    "valor": -restante,
                    "tipo": "fatura",
                }
            )
    eventos.sort(key=lambda item: item["data"])
    pontos = []
    projetado = saldo
    marcos = {30, 60, 90, dias}
    for marco in sorted(item for item in marcos if item <= dias):
        limite = hoje + timedelta(days=marco)
        projetado = saldo + sum(
            (evento["valor"] for evento in eventos if evento["data"] <= limite), Decimal("0")
        )
        pontos.append({"dias": marco, "data": limite, "saldo_projetado": projetado})
    return {"saldo_atual": saldo, "pontos": pontos, "eventos": eventos}


@router.get("/alertas")
def alertas_financeiros(
    dono: str = Query(default="Eu", min_length=1), db: Session = Depends(get_db)
):
    hoje = date.today()
    alertas = []
    for item in status_orcamentos(hoje.month, hoje.year, dono, db):
        if item["situacao"] != "ok":
            alertas.append(
                {
                    "tipo": "orcamento",
                    "severidade": "alta" if item["situacao"] == "estourado" else "media",
                    "mensagem": f"Orcamento da categoria {item['categoria_id']} em {item['percentual']:.0f}%",
                }
            )
    for cartao, mes_ref, ano_ref, _restante in _faturas_abertas_calculadas(db, dono):
        dia = min(cartao.dia_vencimento, calendar.monthrange(ano_ref, mes_ref)[1])
        vencimento = date(ano_ref, mes_ref, dia)
        if vencimento < hoje:
            alertas.append(
                {
                    "tipo": "fatura_atrasada",
                    "severidade": "alta",
                    "mensagem": f"Fatura {cartao.nome} venceu em {vencimento:%d/%m/%Y}",
                }
            )
    recorrencias = db.query(Recorrencia).filter(
        Recorrencia.ativa.is_(True), Recorrencia.proxima_data <= hoje
    ).count()
    if recorrencias:
        alertas.append(
            {
                "tipo": "recorrencias_pendentes",
                "severidade": "media",
                "mensagem": f"{recorrencias} recorrencia(s) aguardando processamento",
            }
        )
    return alertas
