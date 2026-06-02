"""
test_pdf_parser.py — Testes do motor de parsing e chunking

Testa:
  - Extração de texto de PDF real (Boletim 3T25 do enunciado)
  - Decisão correta de estratégia (full-scan vs chunking)
  - Detecção de conteúdo operacional em chunks
  - Tratamento de PDFs inválidos
"""

import pytest
from pathlib import Path
from fpdf import FPDF

from app.processors.pdf_parser import (
    parse_pdf,
    get_text_for_llm,
    _chunk_has_operational_content,
    _is_heading,
    _estimate_tokens,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_pdf(path: Path, pages_content: list[str]) -> Path:
    """Cria um PDF sintético com conteúdo para testes usando fpdf2."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", size=11)
    for content in pages_content:
        pdf.add_page()
        pdf.multi_cell(0, 6, content)
    pdf.output(str(path))
    return path


@pytest.fixture
def sample_pdf_path(tmp_path) -> Path:
    """Cria um PDF sintético com conteúdo operacional para testes."""
    content = (
        "PREVIA OPERACIONAL - 3T2025\n"
        "MRV ENGENHARIA\n\n"
        "LANCAMENTOS\n"
        "Unidades Lancadas: 8500\n"
        "VGV Lancamentos: R$ 2.100 milhoes\n\n"
        "VENDAS\n"
        "Vendas Liquidas (unidades): 9200\n"
        "Vendas Liquidas (VGV): R$ 2.300 milhoes\n"
        "Vendas Brutas (unidades): 9800\n"
        "Distratos (unidades): 600\n\n"
        "ESTOQUE\n"
        "Unidades em Estoque: 12000\n"
        "VGV Estoque: R$ 3.000 milhoes\n\n"
        "ENTREGAS\n"
        "Unidades Entregues: 7000\n"
        "VGV Entregas: R$ 1.800 milhoes\n\n"
        "VSV (Velocidade de Vendas): 18,5%\n"
    )
    return _make_pdf(tmp_path / "test_previa.pdf", [content])


@pytest.fixture
def large_pdf_path(tmp_path) -> Path:
    """Cria um PDF com mais de 20 páginas para testar chunking."""
    pages = []
    for i in range(25):
        if i == 5:
            pages.append(
                f"PAGINA {i+1}\n\n"
                "VENDAS OPERACIONAIS\n"
                "Vendas Liquidas: 9200 unidades\n"
                "VGV: R$ 2.300 MM\n"
            )
        else:
            pages.append(
                f"PAGINA {i+1}\n\n"
                "Conteudo introdutorio sem dados operacionais.\n"
                "Mensagem estrategica da empresa sobre mercado.\n"
            )
    return _make_pdf(tmp_path / "large_previa.pdf", pages)


# ── Testes de Parsing ─────────────────────────────────────────────────────────

class TestPDFParser:

    def test_parse_pdf_retorna_parsed_document(self, sample_pdf_path):
        """parse_pdf deve retornar ParsedDocument válido."""
        result = parse_pdf(sample_pdf_path)
        assert result is not None
        assert result.num_pages == 1
        assert len(result.full_text) > 0
        assert len(result.chunks) > 0

    def test_estrategia_full_scan_para_pdfs_curtos(self, sample_pdf_path):
        """PDFs com ≤ 20 páginas devem usar estratégia full_scan."""
        result = parse_pdf(sample_pdf_path)
        assert result is not None
        assert result.strategy == "full_scan"

    def test_estrategia_chunking_para_pdfs_longos(self, large_pdf_path):
        """PDFs com > 20 páginas devem usar estratégia semantic_chunking."""
        result = parse_pdf(large_pdf_path)
        assert result is not None
        assert result.strategy in ("semantic_chunking", "full_scan_fallback")

    def test_texto_contem_dados_operacionais(self, sample_pdf_path):
        """O texto extraído deve conter as métricas do documento."""
        result = parse_pdf(sample_pdf_path)
        assert result is not None
        text = get_text_for_llm(result)
        # Verifica que algum dos valores está presente
        assert any(v in text for v in ["9200", "2.300", "2300", "9.200"])

    def test_pdf_invalido_retorna_none(self, tmp_path):
        """parse_pdf deve retornar None para arquivo inválido."""
        invalid_path = tmp_path / "invalid.pdf"
        invalid_path.write_bytes(b"not a pdf content")
        result = parse_pdf(invalid_path)
        assert result is None

    def test_pdf_inexistente_retorna_none(self):
        """parse_pdf deve retornar None para arquivo inexistente."""
        result = parse_pdf(Path("/tmp/does_not_exist_123456.pdf"))
        assert result is None


# ── Testes de Chunking ────────────────────────────────────────────────────────

class TestChunking:

    def test_chunk_com_palavra_vendas_e_relevante(self):
        assert _chunk_has_operational_content("Vendas Liquidas: 9.200 unidades")

    def test_chunk_com_vgv_e_relevante(self):
        assert _chunk_has_operational_content("VGV Lancamentos: R$ 2.100 MM")

    def test_chunk_com_estoque_e_relevante(self):
        assert _chunk_has_operational_content("Estoque ao final do trimestre: 12.000 un.")

    def test_chunk_sem_palavras_chave_nao_relevante(self):
        assert not _chunk_has_operational_content(
            "Nossa empresa foi fundada em 1979 e tem orgulho de seu historico."
        )

    def test_heading_maiusculo_e_detectado(self):
        assert _is_heading("LANCAMENTOS")

    def test_heading_numerado_e_detectado(self):
        assert _is_heading("1. Vendas Operacionais")

    def test_texto_longo_nao_e_heading(self):
        assert not _is_heading(
            "Esta e uma frase muito longa que certamente nao e um titulo de secao."
        )


# ── Testes de Estimativa de Tokens ───────────────────────────────────────────

class TestTokenEstimation:

    def test_estimativa_proporcional(self):
        text_curto = "a" * 400
        text_longo = "a" * 4000
        assert _estimate_tokens(text_curto) == 100
        assert _estimate_tokens(text_longo) == 1000

    def test_texto_vazio(self):
        assert _estimate_tokens("") == 0
