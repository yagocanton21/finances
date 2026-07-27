import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}/{os.getenv('POSTGRES_DB')}"

engine = create_engine(
    DATABASE_URL,
    pool_size=10,        # conexões mantidas abertas permanentemente
    max_overflow=20,     # conexões extras permitidas em picos
    pool_pre_ping=True,  # testa a conexão antes de usá-la (evita "connection closed")
    pool_recycle=3600,   # recicla conexões ociosas a cada 1 hora
)

SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


    
