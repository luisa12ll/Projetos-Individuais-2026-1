"""
test_llm_extractor.py — Testes do motor de extração via LLM

Usa mocks para evitar chamadas reais às APIs dos LLMs.
Testa:
  - Parsing correto de resposta JSON do LLM
  - Validação Pydantic (contrato semântico)
  - Sanitização de valores (bilhões → milhões)
  - Tratamento de erros (JSON inválido, campos ausentes)
  - Lógica anti-alucinação (campos ausentes → null)
"""

import json
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from app.models.schema import PreviaPeriodo
from app.processors.llm_extractor import _parse_llm_response


VALID_LLM_RESPONSE = {
    "empresa": "MRV",
    "ano": 2025,
    "trimestre": 3,
    "lancamentos_unidades": 8500,
    "lancamentos_vgv_milhoes": 2100.5,
    "vendas_liquidas_unidades": 9200,
    "vendas_liquidas_vgv_milhoes": 2300.0,
    "vendas_brutas_unidades": 9800,
    "vendas_brutas_vgv_milhoes": 2450.0,
    "distratos_unidades": 600,
    "distratos_vgv_milhoes": 150.0,
    "estoque_unidades": 12000,
    "estoque_vgv_milhoes": 3000.0,
    "entregas_unidades": 7000,
    "entregas_vgv_milhoes": 1800.0,
    "vsv_percentual": 18.5,
    "confianca_extracao": "alta",
}


def _call_parse(data: dict) -> PreviaPeriodo | None:
    """Helper para chamar _parse_llm_response com metadados padrão."""
    return _parse_llm_response(
        raw_json=json.dumps(data),
        empresa="MRV",
        ano=2025,
        trimestre=3,
        fonte_url="https://ri.mrv.com.br/previa_3t25.pdf",
        pdf_hash="abc123def456" * 4,  # 48 chars
        model_name="gemini-1.5-flash",
        pages_used="1-5",
    )


class TestLLMResponseParsing:

    def test_resposta_valida_retorna_previa(self):
        """Resposta JSON válida deve retornar PreviaPeriodo preenchido."""
        result = _call_parse(VALID_LLM_RESPONSE)
        assert result is not None
        assert isinstance(result, PreviaPeriodo)
        assert result.empresa == "MRV"
        assert result.trimestre == 3
        assert result.ano == 2025

    def test_valores_numericos_corretos(self):
        """Valores numéricos devem ser preservados corretamente."""
        result = _call_parse(VALID_LLM_RESPONSE)
        assert result is not None
        assert result.vendas_liquidas_unidades == 9200
        assert result.vendas_liquidas_vgv_milhoes == 2300.0
        assert result.vsv_percentual == 18.5

    def test_confianca_extraida(self):
        """Campo de confiança deve ser preservado."""
        result = _call_parse(VALID_LLM_RESPONSE)
        assert result is not None
        assert result.confianca_extracao == "alta"

    def test_metadados_linhagem_injetados(self):
        """Metadados de linhagem devem ser injetados, não vindos do LLM."""
        result = _call_parse(VALID_LLM_RESPONSE)
        assert result is not None
        assert result.fonte_url == "https://ri.mrv.com.br/previa_3t25.pdf"
        assert result.llm_model_usado == "gemini-1.5-flash"
        assert result.paginas_utilizadas == "1-5"

    def test_empresa_normalizada_para_maiusculas(self):
        """Empresa deve ser normalizada para maiúsculas."""
        data = {**VALID_LLM_RESPONSE, "empresa": "mrv"}
        result = _call_parse(data)
        assert result is not None
        assert result.empresa == "MRV"


class TestCamposAusentes:

    def test_campos_opcionais_ausentes_viram_none(self):
        """Campos ausentes na resposta do LLM devem ser None (não inventar)."""
        data_minima = {
            "empresa": "CURY",
            "ano": 2025,
            "trimestre": 2,
            "vendas_liquidas_unidades": 3000,
            "vendas_liquidas_vgv_milhoes": 900.0,
            "confianca_extracao": "media",
        }
        result = _call_parse(data_minima)
        assert result is not None
        # Campos não informados devem ser None
        assert result.lancamentos_unidades is None
        assert result.estoque_unidades is None
        assert result.entregas_unidades is None
        assert result.distratos_unidades is None

    def test_previa_so_com_obrigatorios(self):
        """PreviaPeriodo deve ser válida mesmo com apenas campos obrigatórios."""
        data_minima = {"empresa": "DIRECIONAL", "ano": 2026, "trimestre": 1}
        result = _call_parse(data_minima)
        assert result is not None
        assert result.empresa == "DIRECIONAL"


class TestSanitizacaoValores:

    def test_vgv_em_bilhoes_convertido_para_milhoes(self):
        """
        Se o LLM retornar VGV como valor muito alto (em reais),
        deve ser convertido para milhões.
        Ex: 2_300_000_000 → 2300.0
        """
        data = {
            **VALID_LLM_RESPONSE,
            "vendas_liquidas_vgv_milhoes": 2_300_000_000,  # reais, não milhões
        }
        result = _call_parse(data)
        assert result is not None
        # Deve ter convertido para milhões
        assert result.vendas_liquidas_vgv_milhoes == 2300.0

    def test_vgv_em_milhoes_preservado(self):
        """VGV já em milhões não deve ser alterado."""
        data = {**VALID_LLM_RESPONSE, "lancamentos_vgv_milhoes": 2100.5}
        result = _call_parse(data)
        assert result is not None
        assert result.lancamentos_vgv_milhoes == 2100.5


class TestTratamentoErros:

    def test_json_invalido_retorna_none(self):
        """JSON malformado deve retornar None sem exceção."""
        from app.processors.llm_extractor import _parse_llm_response
        result = _parse_llm_response(
            raw_json="{ invalid json ]]]",
            empresa="MRV", ano=2025, trimestre=3,
            fonte_url="http://example.com/test.pdf",
            pdf_hash="a" * 64,
            model_name="test",
            pages_used="full",
        )
        assert result is None

    def test_markdown_code_block_limpo(self):
        """JSON envolto em markdown deve ser limpo antes de parsear."""
        data = {**VALID_LLM_RESPONSE}
        json_with_markdown = f"```json\n{json.dumps(data)}\n```"

        from app.processors.llm_extractor import _parse_llm_response
        result = _parse_llm_response(
            raw_json=json_with_markdown,
            empresa="MRV", ano=2025, trimestre=3,
            fonte_url="http://example.com/test.pdf",
            pdf_hash="a" * 64,
            model_name="test",
            pages_used="full",
        )
        assert result is not None
        assert result.empresa == "MRV"

    def test_trimestre_invalido_falha_validacao(self):
        """Trimestre fora do range 1-4 deve falhar na validação Pydantic."""
        data = {**VALID_LLM_RESPONSE, "trimestre": 5}
        result = _call_parse(data)
        assert result is None
