"""
database.py — Modelos SQLAlchemy e inicialização do banco de dados

Usa SQLite para portabilidade máxima (sem infra extra).
Duas tabelas principais:
  - previas_operacionais: dados extraídos pelo LLM
  - catalogo_documentos:  linhagem / rastreabilidade de cada PDF
"""

from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, Float, String,
    Boolean, DateTime, Text, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import StaticPool

from app.config import settings


# ── Engine ───────────────────────────────────────────────────────────────────
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


class Base(DeclarativeBase):
    pass


# ── Tabela: Prévias Operacionais ─────────────────────────────────────────────
class PreviaORM(Base):
    __tablename__ = "previas_operacionais"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identificação temporal
    empresa = Column(String(100), nullable=False, index=True)
    ano = Column(Integer, nullable=False, index=True)
    trimestre = Column(Integer, nullable=False, index=True)

    # Lançamentos
    lancamentos_unidades = Column(Integer, nullable=True)
    lancamentos_vgv_milhoes = Column(Float, nullable=True)

    # Vendas Líquidas
    vendas_liquidas_unidades = Column(Integer, nullable=True)
    vendas_liquidas_vgv_milhoes = Column(Float, nullable=True)

    # Vendas Brutas
    vendas_brutas_unidades = Column(Integer, nullable=True)
    vendas_brutas_vgv_milhoes = Column(Float, nullable=True)

    # Distratos
    distratos_unidades = Column(Integer, nullable=True)
    distratos_vgv_milhoes = Column(Float, nullable=True)

    # Estoque
    estoque_unidades = Column(Integer, nullable=True)
    estoque_vgv_milhoes = Column(Float, nullable=True)

    # Entregas
    entregas_unidades = Column(Integer, nullable=True)
    entregas_vgv_milhoes = Column(Float, nullable=True)

    # Velocidade de Vendas
    vsv_percentual = Column(Float, nullable=True)

    # Evidências (rastreabilidade anti-alucinação, armazenado como JSON serializado)
    evidencias = Column(Text, nullable=True)

    # Linhagem
    fonte_url = Column(Text, nullable=False)
    pdf_hash_sha256 = Column(String(64), nullable=False)
    data_extracao = Column(DateTime, default=datetime.utcnow)
    llm_model_usado = Column(String(100), nullable=True)
    confianca_extracao = Column(String(20), nullable=True)
    paginas_utilizadas = Column(String(50), nullable=True)

    # Unicidade: uma empresa/ano/trimestre por PDF hash
    __table_args__ = (
        UniqueConstraint("empresa", "ano", "trimestre", "pdf_hash_sha256", name="uq_previa_periodo"),
    )

    def __repr__(self):
        return f"<PreviaORM {self.empresa} {self.trimestre}T{self.ano}>"


# ── Tabela: Catálogo de Documentos (Lineage) ─────────────────────────────────
class CatalogoDocumentoORM(Base):
    __tablename__ = "catalogo_documentos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(Text, nullable=False)
    empresa = Column(String(100), nullable=False, index=True)
    ano = Column(Integer, nullable=False)
    trimestre = Column(Integer, nullable=False)
    tipo_documento = Column(String(100), default="previa_operacional")

    # Controle de duplicidade
    pdf_hash_sha256 = Column(String(64), nullable=False, unique=True, index=True)
    nome_arquivo = Column(String(255), nullable=True)
    caminho_local = Column(Text, nullable=True)

    # Status do processamento
    data_download = Column(DateTime, default=datetime.utcnow)
    processado = Column(Boolean, default=False)
    erro_processamento = Column(Text, nullable=True)

    def __repr__(self):
        return f"<CatalogoDocumentoORM {self.empresa} {self.trimestre}T{self.ano} hash={self.pdf_hash_sha256[:8]}>"


# ── Inicialização ─────────────────────────────────────────────────────────────
def init_db() -> None:
    """Cria as tabelas se ainda não existirem."""
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    """Dependency injection para FastAPI."""
    with Session(engine) as session:
        yield session
