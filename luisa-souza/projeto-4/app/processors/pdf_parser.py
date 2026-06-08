"""
pdf_parser.py — Motor de Parsing com suporte a imagens

Estratégia:
  - Extrai texto com pdfplumber (rápido)
  - Converte cada página em imagem com PyMuPDF (para LLMs multimodais)
  - Decisão adaptativa: full-scan ou chunking por número de páginas
"""
import base64
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber

logger = logging.getLogger(__name__)

OPERATIONAL_KEYWORDS = {
    "lançamento", "lancamento", "vgv", "vendas", "venda",
    "unidade", "unidades", "estoque", "entrega", "entregas",
    "distrato", "distratos", "prévia", "previa", "operacional",
    "resultado", "trimestre", "vsv", "vso", "velocidade",
    "mcmv", "minha casa", "programa", "incorporação",
}


@dataclass
class ParsedDocument:
    full_text: str
    pages: list[str]
    chunks: list[str]
    strategy: str
    num_pages: int
    estimated_tokens: int
    pages_used: str
    page_images: list[str] = field(default_factory=list)  # base64 PNG por página


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _pdf_pages_to_images(pdf_path: Path) -> list[str]:
    """
    Converte cada página do PDF em imagem base64 PNG usando PyMuPDF.
    Retorna lista de strings base64, uma por página.
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        images = []
        for page in doc:
            # 2x de zoom para melhor resolução na leitura pelo LLM
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            images.append(img_b64)
        doc.close()
        logger.info(f"[PARSER] {len(images)} página(s) convertida(s) em imagem")
        return images
    except ImportError:
        logger.error("[PARSER] PyMuPDF não instalado — sem suporte a imagens")
        return []
    except Exception as e:
        logger.error(f"[PARSER] Erro ao converter páginas em imagem: {e}")
        return []


def _chunk_has_operational_content(chunk: str) -> bool:
    lower = chunk.lower()
    return any(kw in lower for kw in OPERATIONAL_KEYWORDS)


def _is_heading(text: str) -> bool:
    text = text.strip()
    if not text or len(text) > 120:
        return False
    if text.isupper() and len(text) >= 3:
        return True
    if re.match(r"^[\dIVX]+[\.\)]\s+[A-Z]", text):
        return True
    return False


def _semantic_chunk(pages: list[str], max_chunk_tokens: int = 6000) -> list[str]:
    chunks = []
    current_chunk_lines: list[str] = []
    current_tokens = 0
    for page_text in pages:
        for line in page_text.split("\n"):
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
    try:
        pages: list[str] = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            num_pages = len(pdf.pages)
            logger.info(f"[PARSER] PDF: {pdf_path.name} — {num_pages} páginas")
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                tables = page.extract_tables()
                table_texts = []
                for table in tables:
                    if table:
                        rows = []
                        for row in table:
                            cleaned = [str(cell).strip() if cell else "" for cell in row]
                            rows.append(" | ".join(cleaned))
                        table_texts.append("\n".join(rows))
                page_content = text
                if table_texts:
                    page_content += "\n\n[TABELA]\n" + "\n\n[TABELA]\n".join(table_texts)
                page_content = re.sub(r"\n{3,}", "\n\n", page_content)
                pages.append(page_content)

        full_text = "\n\n".join(
            f"--- PÁGINA {i+1} ---\n{p}" for i, p in enumerate(pages)
        )
        total_tokens = _estimate_tokens(full_text)

        # Converte páginas em imagens para LLMs multimodais
        page_images = _pdf_pages_to_images(pdf_path)

        if num_pages <= 20:
            strategy = "full_scan"
            chunks = [full_text]
            pages_used = f"1-{num_pages}"
            logger.info(f"[PARSER] Estratégia: FULL-SCAN + {len(page_images)} imagens ({num_pages} pág., ~{total_tokens} tokens)")
        else:
            strategy = "semantic_chunking"
            chunks = _semantic_chunk(pages)
            pages_used = f"chunks selecionados de {num_pages} pág."
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
            page_images=page_images,
        )

    except Exception as e:
        logger.error(f"[PARSER] Erro ao processar {pdf_path}: {e}")
        return None


def get_text_for_llm(parsed: ParsedDocument) -> str:
    if len(parsed.chunks) == 1:
        return parsed.chunks[0]
    parts = []
    for i, chunk in enumerate(parsed.chunks, 1):
        parts.append(f"=== SEÇÃO {i} ===\n{chunk}")
    return "\n\n".join(parts)
