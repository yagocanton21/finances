from fastapi import FastAPI
from database import SessionLocal, engine, Base
from models import Categoria, Cartao, GastoDiario

app = FastAPI()
