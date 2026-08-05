import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from database import engine
from routers import agente, aportes_reserva, cartoes, categorias, gastos_diarios, receitas, relatorios

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
    allow_headers=["Content-Type"],
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
