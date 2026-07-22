from fastapi import FastAPI
from database import engine, Base
from models import Categoria, Cartao, GastoDiario
from routers import cartoes, categorias, gastos_diarios, receitas
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="API de Finanças")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permite o frontend em qualquer porta (como a 5173)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"mensagem": "API de Financas esta rodando! Acesse /docs para ver a documentacao."}

app.include_router(cartoes.router, prefix='/cartoes', tags=['cartoes'])
app.include_router(categorias.router, prefix='/categorias', tags=['categorias'])
app.include_router(gastos_diarios.router, prefix='/gastos_diarios', tags=['gastos diários'])
app.include_router(receitas.router, prefix='/receitas', tags=['receitas'])