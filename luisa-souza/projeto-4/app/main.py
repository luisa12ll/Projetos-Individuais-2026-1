"""
main.py — Ponto de Entrada da Aplicação FastAPI

Inicializa:
  1. Banco de dados (SQLite + SQLAlchemy)
  2. Scheduler de coleta automática (APScheduler)
  3. API REST (FastAPI + Uvicorn)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.models.database import init_db
from app.api.routes import router
from app.scheduler.jobs import setup_scheduler, scheduler
from app.config import settings

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup/shutdown) ───────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação."""
    # STARTUP
    logger.info("🚀 Iniciando Pipeline UDA...")

    # Inicializa banco
    init_db()
    logger.info("✅ Banco de dados inicializado")

    # Inicia scheduler
    setup_scheduler()
    logger.info(
        f"✅ Scheduler ativo — próxima coleta: "
        f"{settings.scheduler_hour:02d}:{settings.scheduler_minute:02d} BRT"
    )

    yield

    # SHUTDOWN
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("🛑 Scheduler encerrado")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Pipeline UDA — Conjuntura Habitacional",
    description="""
## Pipeline de Análise de Dados Não Estruturados (UDA)

Sistema automatizado para coleta, extração e disponibilização de dados operacionais
de incorporadoras brasileiras a partir de Prévias Operacionais em PDF.

### Empresas Monitoradas
- **MRV** — ri.mrv.com.br
- **Direcional** — ri.direcional.com.br
- **Cury** — ri.cury.net

### Arquitetura
1. **Coleta**: Scraping diário dos portais de RI com idempotência por SHA-256
2. **Extração UDA**: PyMuPDF + LLM (Gemini Flash / GPT-4o-mini) com contrato semântico Pydantic
3. **API**: Endpoints REST para consulta do Boletim de Conjuntura

### Linhagem dos Dados
Cada registro inclui URL do PDF original, hash SHA-256 e modelo LLM utilizado.
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(router)


@app.get("/", include_in_schema=False)
def root():
    return JSONResponse({
        "servico": "Pipeline UDA — Conjuntura Habitacional",
        "versao": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "health": "/api/health",
            "empresas": "/api/empresas",
            "conjuntura": "/api/conjuntura?empresa=MRV&ano=2025&trimestre=3",
            "catalogo": "/api/catalogo",
        }
    })
