import os
import logging
import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app_logging import configure_logging, normalize_request_id, request_id_context
from database import engine
from routers import agente, aportes_reserva, cartoes, categorias, gastos_diarios, receitas, relatorios

configure_logging()
logger = logging.getLogger("financas.http")
app = FastAPI(title="API de Financas")

origens = [
    origem.strip()
    for origem in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(",")
    if origem.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origens,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def registrar_requisicao(request: Request, call_next):
    recebido = request.headers.get("X-Request-ID", "")
    request_id = normalize_request_id(recebido)
    request.state.request_id = request_id
    token = request_id_context.set(request_id)
    inicio = time.perf_counter()
    client_ip = request.headers.get("X-Forwarded-For")
    if not client_ip and request.client:
        client_ip = request.client.host

    try:
        response = await call_next(request)
        duracao_ms = round((time.perf_counter() - inicio) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        if request.url.path != "/health" or response.status_code >= 400:
            nivel = logging.ERROR if response.status_code >= 500 else logging.INFO
            logger.log(
                nivel,
                "Requisicao concluida",
                extra={
                    "event": "http_request",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duracao_ms,
                    "client_ip": client_ip,
                },
            )
        return response
    except Exception:
        duracao_ms = round((time.perf_counter() - inicio) * 1000, 2)
        logger.exception(
            "Erro nao tratado durante requisicao",
            extra={
                "event": "http_request_error",
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "duration_ms": duracao_ms,
                "client_ip": client_ip,
            },
        )
        raise
    finally:
        request_id_context.reset(token)


@app.exception_handler(Exception)
async def erro_nao_tratado(request: Request, _exc: Exception):
    error_id = getattr(request.state, "request_id", uuid4().hex)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor", "error_id": error_id},
        headers={"X-Request-ID": error_id},
    )


@app.get("/")
def read_root():
    return {
        "mensagem": "API de Financas esta rodando. Acesse /docs para a documentacao."
    }


@app.get("/health")
def health():
    with engine.connect() as conexao:
        conexao.execute(text("SELECT 1"))
    return {"status": "ok"}


app.include_router(cartoes.router, prefix="/cartoes", tags=["cartoes"])
app.include_router(categorias.router, prefix="/categorias", tags=["categorias"])
app.include_router(
    gastos_diarios.router, prefix="/gastos_diarios", tags=["gastos diarios"]
)
app.include_router(receitas.router, prefix="/receitas", tags=["receitas"])
app.include_router(relatorios.router, prefix="/relatorios", tags=["relatorios"])
app.include_router(aportes_reserva.router, prefix="/aportes_reserva", tags=["reserva"])
app.include_router(agente.router, prefix="/agent/v1", tags=["integracao Hermes"])
