"""
docling_parser.py — Parser alternativo usando Docling

Docling converte PDFs em Markdown estruturado, preservando tabelas
mesmo em PDFs com texto rotacionado ou em slides (como a MRV).
Usado como fallback quando pdfplumber extrai texto embaralhado.
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def parse_pdf_to_markdown(pdf_path: Path) -> Optional[str]:
    """
    Converte um PDF em Markdown usando Docling.
    Preserva tabelas e estrutura mesmo em layouts complexos.
    """
    try:
        from docling.document_converter import DocumentConverter

        logger.info(f"[DOCLING] Convertendo: {pdf_path.name}")
        converter = DocumentConverter()
        result = converter.convert(str(pdf_path))
        markdown = result.document.export_to_markdown()
        logger.info(f"[DOCLING] Convertido: {len(markdown)} chars")
        return markdown

    except Exception as e:
        logger.error(f"[DOCLING] Falha: {e}")
        return None
