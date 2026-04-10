from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# En producción en AWS, cambiarías esto por la URL de tu base de datos
SQLALCHEMY_DATABASE_URL = "sqlite:///./finanzas_contratistas.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Inyección de dependencias para FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()