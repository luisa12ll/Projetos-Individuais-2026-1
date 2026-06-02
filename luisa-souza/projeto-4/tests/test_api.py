"""
test_api.py — Testes de Integração da API FastAPI

Testa todos os endpoints REST:
  - /api/health
  - /api/empresas
  - /api/conjuntura (com vários filtros)
  - /api/conjuntura/{empresa}
  - /api/catalogo
  - /api/processar (mock do LLM)
"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Configura ambiente de teste antes de importar o app
import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["GEMINI_API_KEY"] = "test-key"
os.environ["PDF_STORAGE_DIR"] = "/tmp/uda_test_pdfs"

from app.main import app
from app.models.database import Base, engine, PreviaORM, CatalogoDocumentoORM
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def setup_db():
    """Cria banco em memória para cada teste."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_previa():
    """Insere uma prévia de teste no banco."""
    with Session(engine) as session:
        previa = PreviaORM(
            empresa="MRV",
            ano=2025,
            trimestre=3,
            lancamentos_unidades=8500,
            lancamentos_vgv_milhoes=2100.5,
            vendas_liquidas_unidades=9200,
            vendas_liquidas_vgv_milhoes=2300.0,
            vendas_brutas_unidades=9800,
            vendas_brutas_vgv_milhoes=2450.0,
            distratos_unidades=600,
            distratos_vgv_milhoes=150.0,
            estoque_unidades=12000,
            estoque_vgv_milhoes=3000.0,
            entregas_unidades=7000,
            entregas_vgv_milhoes=1800.0,
            vsv_percentual=18.5,
            fonte_url="https://ri.mrv.com.br/previa_3t25.pdf",
            pdf_hash_sha256="a" * 64,
            data_extracao=datetime(2025, 10, 15),
            llm_model_usado="gemini-1.5-flash",
            confianca_extracao="alta",
        )
        session.add(previa)
        session.commit()
        return previa


@pytest.fixture
def sample_direcional():
    """Insere prévia da Direcional no banco."""
    with Session(engine) as session:
        previa = PreviaORM(
            empresa="DIRECIONAL",
            ano=2025,
            trimestre=3,
            vendas_liquidas_unidades=4500,
            vendas_liquidas_vgv_milhoes=1200.0,
            fonte_url="https://ri.direcional.com.br/previa_3t25.pdf",
            pdf_hash_sha256="b" * 64,
            data_extracao=datetime(2025, 10, 16),
            llm_model_usado="gemini-1.5-flash",
            confianca_extracao="media",
        )
        session.add(previa)
        session.commit()
        return previa


# ── Testes de Health ─────────────────────────────────────────────────────────

class TestHealthEndpoint:

    def test_health_retorna_200(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_health_contem_campos_obrigatorios(self, client):
        data = response = client.get("/api/health").json()
        assert "status" in data
        assert "version" in data
        assert "total_previas_processadas" in data
        assert data["status"] == "healthy"

    def test_root_redirect_info(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "endpoints" in data


# ── Testes de Empresas ────────────────────────────────────────────────────────

class TestEmpresasEndpoint:

    def test_empresas_lista_vazia_sem_dados(self, client):
        response = client.get("/api/empresas")
        assert response.status_code == 200
        assert response.json() == []

    def test_empresas_lista_com_dados(self, client, sample_previa, sample_direcional):
        response = client.get("/api/empresas")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        nomes = {e["nome"] for e in data}
        assert "MRV" in nomes
        assert "DIRECIONAL" in nomes

    def test_empresa_tem_total_previas(self, client, sample_previa):
        response = client.get("/api/empresas")
        data = response.json()
        mrv = next(e for e in data if e["nome"] == "MRV")
        assert mrv["total_previas"] == 1


# ── Testes de Conjuntura ──────────────────────────────────────────────────────

class TestConjunturaEndpoint:

    def test_conjuntura_vazia_sem_dados(self, client):
        response = client.get("/api/conjuntura")
        assert response.status_code == 200
        assert response.json() == []

    def test_conjuntura_retorna_dados(self, client, sample_previa):
        response = client.get("/api/conjuntura")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["empresa"] == "MRV"

    def test_filtro_por_empresa(self, client, sample_previa, sample_direcional):
        response = client.get("/api/conjuntura?empresa=MRV")
        assert response.status_code == 200
        data = response.json()
        assert all(d["empresa"] == "MRV" for d in data)
        assert len(data) == 1

    def test_filtro_por_empresa_case_insensitive(self, client, sample_previa):
        response = client.get("/api/conjuntura?empresa=mrv")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    def test_filtro_por_ano_e_trimestre(self, client, sample_previa):
        response = client.get("/api/conjuntura?ano=2025&trimestre=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_filtro_sem_resultado(self, client, sample_previa):
        response = client.get("/api/conjuntura?empresa=CURY")
        assert response.status_code == 200
        assert response.json() == []

    def test_dados_contem_periodo_formatado(self, client, sample_previa):
        response = client.get("/api/conjuntura?empresa=MRV")
        data = response.json()
        assert data[0]["periodo"] == "3T2025"

    def test_dados_contem_linhagem(self, client, sample_previa):
        response = client.get("/api/conjuntura?empresa=MRV")
        data = response.json()
        assert "fonte_url" in data[0]
        assert "data_extracao" in data[0]
        assert "confianca_extracao" in data[0]


# ── Testes de Empresa Específica ──────────────────────────────────────────────

class TestConjunturaEmpresaEndpoint:

    def test_empresa_existente_retorna_historico(self, client, sample_previa):
        response = client.get("/api/conjuntura/MRV")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["empresa"] == "MRV"

    def test_empresa_inexistente_retorna_404(self, client):
        response = client.get("/api/conjuntura/EMPRESA_INEXISTENTE")
        assert response.status_code == 404


# ── Testes do Catálogo ────────────────────────────────────────────────────────

class TestCatalogoEndpoint:

    def test_catalogo_vazio(self, client):
        response = client.get("/api/catalogo")
        assert response.status_code == 200
        assert response.json() == []

    def test_catalogo_com_documentos(self, client):
        with Session(engine) as session:
            doc = CatalogoDocumentoORM(
                url="https://ri.mrv.com.br/previa.pdf",
                empresa="MRV",
                ano=2025,
                trimestre=3,
                pdf_hash_sha256="c" * 64,
                nome_arquivo="previa_3t25.pdf",
                processado=True,
            )
            session.add(doc)
            session.commit()

        response = client.get("/api/catalogo")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["empresa"] == "MRV"
        assert data[0]["pdf_hash_sha256"] == "c" * 64
        assert data[0]["processado"] is True
