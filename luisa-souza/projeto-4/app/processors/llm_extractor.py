"""
llm_extractor.py — Motor de Extração via LLM Multimodal

Usa GitHub Models (gpt-4o-mini) com suporte a imagens.
Estratégia adaptativa:
  - PDF com texto legível (>2000 tokens): usa texto + 2 imagens iniciais
  - PDF com texto ruim/embaralhado (<2000 tokens): usa só imagens do meio do doc
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


def _call_github_models(
    system_prompt: str,
    user_prompt: str,
    page_images: list[str],
    doc_tokens: int = 0,
    empresa_hint: str = '',
) -> Optional[str]:
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url="https://models.inference.ai.azure.com",
            api_key=settings.github_token,
        )
        total = len(page_images)
        has_good_text = doc_tokens > 2000

        if not has_good_text:
            # PDF com texto ruim (slides/rotacionado): usa só imagens do meio
            prompt_text = (
                f"Analise as imagens do PDF de prévia operacional da empresa {empresa_hint}. "
                f"O período do relatório é {empresa_hint} - busque a coluna '1T26' ou o período mais à esquerda da tabela. "
                "Extraia os dados da tabela INDICADORES OPERACIONAIS - LANÇAMENTOS e VENDAS LÍQUIDAS. "
                "Retorne JSON com: lancamentos_unidades, lancamentos_vgv_milhoes, "
                "vendas_liquidas_unidades, vendas_liquidas_vgv_milhoes, "
                "vendas_brutas_unidades, vendas_brutas_vgv_milhoes, "
                "distratos_unidades, distratos_vgv_milhoes, estoque_unidades, estoque_vgv_milhoes, "
                "entregas_unidades, entregas_vgv_milhoes, vsv_percentual, confianca_extracao. "
                "IMPORTANTE: Use a linha TOTAL INCORPORAÇÃO. "
                "A coluna correta é a PRIMEIRA coluna de dados (mais à esquerda), não as colunas de comparação. "
                "Os valores devem ser na casa dos MILHARES de unidades e MILHÕES de reais. "
                "Campos ausentes = null."
            )
            # Manda só a página do meio com alta resolução para leitura precisa da tabela
            mid = int(total * 0.50)
            selected_indices = [mid]
        else:
            # PDF com texto legível: usa texto + 2 primeiras páginas
            prompt_text = user_prompt
            selected_indices = list(range(min(2, total)))

        content = [{"type": "text", "text": prompt_text}]
        for idx in selected_indices:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{page_images[idx]}",
                    "detail": "high" if not has_good_text else "low",
                }
            })

        logger.info(f"[LLM] Enviando páginas {[i+1 for i in selected_indices]} de {total} (texto_ok={has_good_text})")

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=2048,
        )
        logger.info(f"[LLM] GitHub Models respondeu ({len(selected_indices)} imagens, texto_ok={has_good_text})")
        return response.choices[0].message.content

    except Exception as e:
        logger.warning(f"[LLM] GitHub Models falhou: {e}")
        return None


def _call_llm(
    system_prompt: str,
    user_prompt: str,
    page_images: list[str],
    doc_tokens: int = 0,
    empresa_hint: str = '',
) -> tuple[Optional[str], str]:
    result = _call_github_models(system_prompt, user_prompt, page_images, doc_tokens, empresa_hint)
    if result:
        return result, "gpt-4o-mini (github-models)"
    return None, "none"


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
    try:
        cleaned = raw_json.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned

        data = json.loads(cleaned)
        data["fonte_url"] = fonte_url
        data["pdf_hash_sha256"] = pdf_hash
        data["llm_model_usado"] = model_name
        data["data_extracao"] = datetime.utcnow().isoformat()
        data["paginas_utilizadas"] = pages_used
        data.setdefault("empresa", empresa)
        data.setdefault("ano", ano)
        data.setdefault("trimestre", trimestre)

        previa = PreviaPeriodo(**data)
        logger.info(f"[EXTRACTOR] Validado: {previa.empresa} {previa.trimestre}T{previa.ano} [confiança: {previa.confianca_extracao}]")
        return previa

    except json.JSONDecodeError as e:
        logger.error(f"[EXTRACTOR] JSON inválido: {e}")
        return None
    except ValidationError as e:
        logger.error(f"[EXTRACTOR] Validação Pydantic falhou: {e}")
        return None


def _persist_previa(previa: PreviaPeriodo) -> bool:
    try:
        with Session(engine) as session:
            orm = PreviaORM(
                empresa=previa.empresa, ano=previa.ano, trimestre=previa.trimestre,
                evidencias=json.dumps(previa.evidencias, ensure_ascii=False) if previa.evidencias else None,
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
            session.merge(orm)
            session.commit()
            logger.info(f"[DB] Persistido: {previa.empresa} {previa.trimestre}T{previa.ano}")
            return True
    except Exception as e:
        logger.error(f"[DB] Falha ao persistir: {e}")
        return False


def extract_and_persist(
    pdf_path: Path,
    parsed_doc: ParsedDocument,
    empresa: str,
    ano: int,
    trimestre: int,
    fonte_url: str,
    pdf_hash: str,
) -> Optional[PreviaPeriodo]:
    logger.info(f"[EXTRACTOR] Iniciando: {empresa} {trimestre}T{ano}")

    document_text = get_text_for_llm(parsed_doc)
    if len(document_text) > 100_000:
        document_text = document_text[:100_000] + "\n\n[DOCUMENTO TRUNCADO]"

    system_prompt = build_system_prompt(empresa, ano, trimestre)
    user_prompt = build_user_prompt(document_text, empresa, ano, trimestre)

    raw_json, model_name = _call_llm(
        system_prompt, user_prompt,
        parsed_doc.page_images,
        parsed_doc.estimated_tokens,
        empresa
    )

    if not raw_json:
        logger.error(f"[EXTRACTOR] LLM falhou para {empresa} {trimestre}T{ano}")
        return None

    previa = _parse_llm_response(
        raw_json=raw_json, empresa=empresa, ano=ano, trimestre=trimestre,
        fonte_url=fonte_url, pdf_hash=pdf_hash, model_name=model_name,
        pages_used=parsed_doc.pages_used,
    )
    if not previa:
        return None

    success = _persist_previa(previa)
    return previa if success else None
