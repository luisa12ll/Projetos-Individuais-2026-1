"""
pdf_parser.py — Motor de Parsing com Docling + fallback pdfplumber

Estratégia:
  1. Docling (primário) — converte PDF em Markdown estruturado, lê tabelas rotacionadas
  2. pdfplumber (fallback) — se Docling falhar
  3. PyMuPDF — converte páginas em imagens para LLMs multimodais
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
    page_images: list[str] = field(default_factory=list)


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _pdf_pages_to_images(pdf_path: Path) -> list[str]:
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        images = []
        for page in doc:
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            images.append(base64.b64encode(img_bytes).decode("utf-8"))
        doc.close()
        logger.info(f"[PARSER] {len(images)} página(s) convertida(s) em imagem")
        return images
    except Exception as e:
        logger.error(f"[PARSER] Erro ao converter imagens: {e}")
        return []


def _parse_with_docling(pdf_path: Path) -> Optional[tuple[str, int]]:
    """Retorna (markdown_text, num_pages) ou None se falhar."""
    try:
        from docling.document_converter import DocumentConverter
        import warnings
        warnings.filterwarnings("ignore")
        converter = DocumentConverter()
        result = converter.convert(str(pdf_path))
        md = result.document.export_to_markdown()
        num_pages = len(result.document.pages) if hasattr(result.document, 'pages') else 1
        logger.info(f"[PARSER] Docling: {len(md)} chars, ~{_estimate_tokens(md)} tokens")
        return md, num_pages
    except Exception as e:
        logger.warning(f"[PARSER] Docling falhou: {e}")
        return None


def _parse_with_pdfplumber(pdf_path: Path) -> tuple[str, list[str], int]:
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        num_pages = len(pdf.pages)
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            tables = page.extract_tables()
            table_texts = []
            for table in tables:
                if table:
                    rows = [" | ".join(str(c).strip() if c else "" for c in row) for row in table]
                    table_texts.append("\n".join(rows))
            page_content = text
            if table_texts:
                page_content += "\n\n[TABELA]\n" + "\n\n[TABELA]\n".join(table_texts)
            pages.append(re.sub(r"\n{3,}", "\n\n", page_content))
    full_text = "\n\n".join(f"--- PÁGINA {i+1} ---\n{p}" for i, p in enumerate(pages))
    return full_text, pages, num_pages


def parse_pdf(pdf_path: Path) -> Optional[ParsedDocument]:
    try:
        page_images = _pdf_pages_to_images(pdf_path)

        # Tenta Docling primeiro
        docling_result = _parse_with_docling(pdf_path)

        if docling_result:
            full_text, num_pages = docling_result
            strategy = "docling"
            pages = [full_text]
            if num_pages == 1:
                num_pages = max(1, len(page_images))
        else:
            # Fallback pdfplumber
            full_text, pages, num_pages = _parse_with_pdfplumber(pdf_path)
            strategy = "pdfplumber_fallback"

        total_tokens = _estimate_tokens(full_text)
        pages_used = f"1-{num_pages}"

        logger.info(f"[PARSER] {pdf_path.name} — {num_pages} pág., ~{total_tokens} tokens, estratégia: {strategy}")

        return ParsedDocument(
            full_text=full_text,
            pages=pages,
            chunks=[full_text],
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
    return "\n\n".join(f"=== SEÇÃO {i} ===\n{c}" for i, c in enumerate(parsed.chunks, 1))
