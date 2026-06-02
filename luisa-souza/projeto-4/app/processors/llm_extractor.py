"""
llm_extractor.py — Motor de Extração via LLM

Orquestra a chamada ao LLM (Gemini Flash com fallback OpenAI),
valida a resposta com Pydantic e persiste no banco de dados.

Fluxo:
  1. Tenta Gemini Flash (gratuito, alta capacidade de contexto)
  2. Fallback: GPT-4o-mini (se Gemini falhar ou não configurado)
  3. Valida JSON com PreviaPeriodo Pydantic
  4. Persiste no banco via SQLAlchemy
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.config import settings
from app.models.schema import PreviaPeriodo
from app.models.database import PreviaORM, engine
from app.processors.pdf_parser import ParsedDocument, get_text_for_llm
from app.processors.prompt_builder import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)


# ── Clientes LLM ─────────────────────────────────────────────────────────────

def _call_gemini(system_prompt: str, user_prompt: str) -> Optional[str]:
    """Chama a API do Google Gemini Flash e retorna o JSON extraído."""
    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=system_prompt,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.0,  # determinístico para extração
                "max_output_tokens": 2048,
            }
        )
        response = model.generate_content(user_prompt)
        logger.info("[LLM] Gemini Flash respondeu com sucesso")
        return response.text

    except Exception as e:
        logger.warning(f"[LLM] Gemini falhou: {e}")
        return None


def _call_openai(system_prompt: str, user_prompt: str) -> Optional[str]:
    """Chama a API da OpenAI (GPT-4o-mini) como fallback."""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=2048,
        )
        logger.info("[LLM] GPT-4o-mini respondeu com sucesso")
        return response.choices[0].message.content

    except Exception as e:
        logger.warning(f"[LLM] OpenAI falhou: {e}")
        return None


def _call_llm(system_prompt: str, user_prompt: str) -> tuple[Optional[str], str]:
    """
    Tenta Gemini primeiro; se falhar, tenta OpenAI.
    Retorna (json_string, model_name_used).
    """
    if settings.has_gemini:
        result = _call_gemini(system_prompt, user_prompt)
        if result:
            return result, "gemini-1.5-flash"

    if settings.has_openai:
        result = _call_openai(system_prompt, user_prompt)
        if result:
            return result, "gpt-4o-mini"

    return None, "none"


# ── Parser de resposta ────────────────────────────────────────────────────────

def _parse_llm_response(
    raw_json: str,
    empresa: str,
    ano: int,
    trimestre: int,
    fonte_url: str,
    pdf_hash: str,
    model_name: str,
    pages_used: str,
) -> Optional[PreviaPeriodo]:
    """
    Valida e completa a resposta do LLM usando Pydantic.
    Injeta metadados de linhagem que o LLM não preenche.
    """
    try:
        # Limpa markdown caso o modelo ignore a instrução de não usar
        cleaned = raw_json.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:-1])

        data = json.loads(cleaned)

        # Injeta metadados de linhagem (não devem vir do LLM)
        data["fonte_url"] = fonte_url
        data["pdf_hash_sha256"] = pdf_hash
        data["llm_model_usado"] = model_name
        data["data_extracao"] = datetime.utcnow().isoformat()
        data["paginas_utilizadas"] = pages_used

        # Garante que empresa/ano/trimestre sejam os esperados
        # (o LLM pode identificar diferente — usamos o que coletamos)
        data.setdefault("empresa", empresa)
        data.setdefault("ano", ano)
        data.setdefault("trimestre", trimestre)

        previa = PreviaPeriodo(**data)
        logger.info(
            f"[EXTRACTOR] Extração validada: {previa.empresa} "
            f"{previa.trimestre}T{previa.ano} "
            f"[confiança: {previa.confianca_extracao}]"
        )
        return previa

    except json.JSONDecodeError as e:
        logger.error(f"[EXTRACTOR] JSON inválido do LLM: {e}")
        logger.debug(f"[EXTRACTOR] Resposta bruta: {raw_json[:500]}")
        return None
    except ValidationError as e:
        logger.error(f"[EXTRACTOR] Validação Pydantic falhou: {e}")
        return None


# ── Persistência ──────────────────────────────────────────────────────────────

def _persist_previa(previa: PreviaPeriodo) -> bool:
    """Salva os dados extraídos no banco de dados."""
    try:
        with Session(engine) as session:
            orm = PreviaORM(
                empresa=previa.empresa,
                ano=previa.ano,
                trimestre=previa.trimestre,
                lancamentos_unidades=previa.lancamentos_unidades,
                lancamentos_vgv_milhoes=previa.lancamentos_vgv_milhoes,
                vendas_liquidas_unidades=previa.vendas_liquidas_unidades,
                vendas_liquidas_vgv_milhoes=previa.vendas_liquidas_vgv_milhoes,
                vendas_brutas_unidades=previa.vendas_brutas_unidades,
                vendas_brutas_vgv_milhoes=previa.vendas_brutas_vgv_milhoes,
                distratos_unidades=previa.distratos_unidades,
                distratos_vgv_milhoes=previa.distratos_vgv_milhoes,
                estoque_unidades=previa.estoque_unidades,
                estoque_vgv_milhoes=previa.estoque_vgv_milhoes,
                entregas_unidades=previa.entregas_unidades,
                entregas_vgv_milhoes=previa.entregas_vgv_milhoes,
                vsv_percentual=previa.vsv_percentual,
                fonte_url=previa.fonte_url,
                pdf_hash_sha256=previa.pdf_hash_sha256,
                data_extracao=previa.data_extracao,
                llm_model_usado=previa.llm_model_usado,
                confianca_extracao=previa.confianca_extracao,
                paginas_utilizadas=previa.paginas_utilizadas,
            )
            session.merge(orm)  # merge evita duplicatas pela constraint única
            session.commit()
            logger.info(f"[DB] Persistido: {previa.empresa} {previa.trimestre}T{previa.ano}")
            return True

    except Exception as e:
        logger.error(f"[DB] Falha ao persistir: {e}")
        return False


# ── Função Principal ──────────────────────────────────────────────────────────

def extract_and_persist(
    pdf_path: Path,
    parsed_doc: ParsedDocument,
    empresa: str,
    ano: int,
    trimestre: int,
    fonte_url: str,
    pdf_hash: str,
) -> Optional[PreviaPeriodo]:
    """
    Pipeline completo de extração:
    1. Monta prompts
    2. Chama LLM (Gemini → OpenAI fallback)
    3. Valida com Pydantic
    4. Persiste no banco

    Returns:
        PreviaPeriodo se sucesso, None se falhou
    """
    logger.info(f"[EXTRACTOR] Iniciando extração: {empresa} {trimestre}T{ano}")

    # ── 1. Prepara texto para o LLM ──────────────────────────────────────────
    document_text = get_text_for_llm(parsed_doc)

    # Limita tamanho para não explodir contexto (aprox 100k chars = ~25k tokens)
    if len(document_text) > 100_000:
        logger.warning(f"[EXTRACTOR] Texto muito longo ({len(document_text)} chars) — truncando")
        document_text = document_text[:100_000] + "\n\n[DOCUMENTO TRUNCADO]"

    # ── 2. Monta prompts ─────────────────────────────────────────────────────
    system_prompt = build_system_prompt(empresa, ano, trimestre)
    user_prompt = build_user_prompt(document_text, empresa, ano, trimestre)

    logger.info(
        f"[EXTRACTOR] Estratégia: {parsed_doc.strategy} | "
        f"~{parsed_doc.estimated_tokens} tokens estimados | "
        f"{len(parsed_doc.chunks)} chunk(s)"
    )

    # ── 3. Chama o LLM ───────────────────────────────────────────────────────
    raw_json, model_name = _call_llm(system_prompt, user_prompt)

    if not raw_json:
        logger.error(f"[EXTRACTOR] Todos os LLMs falharam para {empresa} {trimestre}T{ano}")
        return None

    # ── 4. Valida e completa ─────────────────────────────────────────────────
    previa = _parse_llm_response(
        raw_json=raw_json,
        empresa=empresa,
        ano=ano,
        trimestre=trimestre,
        fonte_url=fonte_url,
        pdf_hash=pdf_hash,
        model_name=model_name,
        pages_used=parsed_doc.pages_used,
    )

    if not previa:
        return None

    # ── 5. Persiste ──────────────────────────────────────────────────────────
    success = _persist_previa(previa)
    return previa if success else None
