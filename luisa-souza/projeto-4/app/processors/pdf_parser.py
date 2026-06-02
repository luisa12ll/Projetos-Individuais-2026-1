"""
pdf_parser.py — Motor de Parsing e Chunking Adaptativo de PDFs

Estratégia Híbrida:
  - Full-Scan: documentos com até FULL_SCAN_MAX_PAGES páginas → envia texto integral
  - Chunking Semântico: documentos maiores → divide por seções/títulos e filtra
    chunks com palavras-chave operacionais

Usa pdfplumber (puro Python, sem dependências de compilação).
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber

from app.config import settings

logger = logging.getLogger(__name__)

# ── Palavras-chave que indicam seções com dados operacionais ─────────────────
OPERATIONAL_KEYWORDS = {
    "lançamento", "lancamento", "vgv", "vendas", "venda",
    "unidade", "unidades", "estoque", "entrega", "entregas",
    "distrato", "distratos", "prévia", "previa", "operacional",
    "resultado", "trimestre", "vsv", "vso", "velocidade",
    "mcmv", "minha casa", "programa", "incorporação",
}


@dataclass
class ParsedDocument:
    """Resultado do parsing de um PDF."""
    full_text: str
    pages: list[str]       # texto por página
    chunks: list[str]      # chunks semânticos (se chunking foi aplicado)
    strategy: str          # "full_scan" ou "semantic_chunking"
    num_pages: int
    estimated_tokens: int
    pages_used: str        # ex: "1-10" ou "full"


def _estimate_tokens(text: str) -> int:
    """Estimativa simples: ~4 caracteres por token (heurística GPT)."""
    return len(text) // 4


def _is_heading(text: str) -> bool:
    """
    Detecta se uma linha parece ser um título/heading.
    Heurística: linha curta, em maiúsculas ou com padrão de numeração.
    """
    text = text.strip()
    if not text or len(text) > 120:
        return False
    if text.isupper() and len(text) >= 3:
        return True
    if re.match(r"^[\dIVX]+[\.\)]\s+[A-Z]", text):
        return True
    return False


def _chunk_has_operational_content(chunk: str) -> bool:
    """Verifica se um chunk contém informações operacionais relevantes."""
    lower = chunk.lower()
    return any(kw in lower for kw in OPERATIONAL_KEYWORDS)


def _semantic_chunk(pages: list[str], max_chunk_tokens: int = 6000) -> list[str]:
    """
    Divide o documento em chunks semânticos baseados em headings detectados.
    Retorna apenas chunks com conteúdo operacional relevante.
    """
    chunks = []
    current_chunk_lines: list[str] = []
    current_tokens = 0

    for page_text in pages:
        lines = page_text.split("\n")
        for line in lines:
            line_tokens = _estimate_tokens(line)

            if _is_heading(line) and current_chunk_lines:
                chunk_text = "\n".join(current_chunk_lines).strip()
                if chunk_text and _chunk_has_operational_content(chunk_text):
                    chunks.append(chunk_text)
                current_chunk_lines = [line]
                current_tokens = line_tokens
            else:
                if current_tokens + line_tokens > max_chunk_tokens:
                    chunk_text = "\n".join(current_chunk_lines).strip()
                    if chunk_text and _chunk_has_operational_content(chunk_text):
                        chunks.append(chunk_text)
                    current_chunk_lines = [line]
                    current_tokens = line_tokens
                else:
                    current_chunk_lines.append(line)
                    current_tokens += line_tokens

    if current_chunk_lines:
        chunk_text = "\n".join(current_chunk_lines).strip()
        if chunk_text and _chunk_has_operational_content(chunk_text):
            chunks.append(chunk_text)

    return chunks


def parse_pdf(pdf_path: Path) -> Optional[ParsedDocument]:
    """
    Estratégia Adaptativa de Parsing:

    1. Abre o PDF com pdfplumber
    2. Extrai texto página a página (texto + tabelas como texto)
    3. Decide estratégia:
       a. Full-Scan: se num_páginas ≤ FULL_SCAN_MAX_PAGES
       b. Chunking Semântico: se num_páginas > FULL_SCAN_MAX_PAGES
    4. Filtra chunks sem conteúdo operacional
    """
    try:
        pages: list[str] = []

        with pdfplumber.open(str(pdf_path)) as pdf:
            num_pages = len(pdf.pages)
            logger.info(f"[PARSER] PDF: {pdf_path.name} — {num_pages} páginas")

            for page in pdf.pages:
                # Extrai texto livre
                text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""

                # Extrai tabelas e converte para texto tabular
                tables = page.extract_tables()
                table_texts = []
                for table in tables:
                    if table:
                        rows = []
                        for row in table:
                            cleaned = [str(cell).strip() if cell else "" for cell in row]
                            rows.append(" | ".join(cleaned))
                        table_texts.append("\n".join(rows))

                # Combina texto livre + tabelas
                page_content = text
                if table_texts:
                    page_content += "\n\n[TABELA]\n" + "\n\n[TABELA]\n".join(table_texts)

                # Remove excesso de espaços em branco
                page_content = re.sub(r"\n{3,}", "\n\n", page_content)
                pages.append(page_content)

        full_text = "\n\n".join(
            f"--- PÁGINA {i+1} ---\n{p}" for i, p in enumerate(pages)
        )
        total_tokens = _estimate_tokens(full_text)

        # ── Decisão: Full-Scan vs. Chunking ──────────────────────────────────
        if num_pages <= settings.full_scan_max_pages:
            strategy = "full_scan"
            chunks = [full_text]
            pages_used = f"1-{num_pages}"
            logger.info(
                f"[PARSER] Estratégia: FULL-SCAN ({num_pages} pág., ~{total_tokens} tokens)"
            )
        else:
            strategy = "semantic_chunking"
            chunks = _semantic_chunk(pages)
            pages_used = f"chunks selecionados de {num_pages} pág."
            logger.info(
                f"[PARSER] Estratégia: CHUNKING SEMÂNTICO — "
                f"{len(chunks)} chunks relevantes de {num_pages} pág."
            )

            if not chunks:
                logger.warning("[PARSER] Nenhum chunk relevante — fallback para full-scan")
                strategy = "full_scan_fallback"
                chunks = [full_text[:32000]]
                pages_used = f"1-{num_pages} (truncado)"

        return ParsedDocument(
            full_text=full_text,
            pages=pages,
            chunks=chunks,
            strategy=strategy,
            num_pages=num_pages,
            estimated_tokens=total_tokens,
            pages_used=pages_used,
        )

    except Exception as e:
        logger.error(f"[PARSER] Erro ao processar {pdf_path}: {e}")
        return None


def get_text_for_llm(parsed: ParsedDocument) -> str:
    """Concatena chunks em uma string única para o LLM."""
    if len(parsed.chunks) == 1:
        return parsed.chunks[0]

    parts = []
    for i, chunk in enumerate(parsed.chunks, 1):
        parts.append(f"=== SEÇÃO {i} ===\n{chunk}")

    return "\n\n".join(parts)
