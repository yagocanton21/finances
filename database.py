import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

campos_obrigatorios = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
ausentes = [campo for campo in campos_obrigatorios if not os.getenv(campo)]
if ausentes:
    raise RuntimeError(
        f"Variaveis de banco ausentes: {', '.join(ausentes)}"
    )

DATABASE_URL = (
    f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
    f"@{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5432')}/{os.environ['POSTGRES_DB']}"
)

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
