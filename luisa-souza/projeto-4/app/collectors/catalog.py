"""
catalog.py — Catálogo de Dados e Linhagem (Data Lineage)

Responsável por:
  - Verificar se um PDF já foi processado (idempotência via SHA-256)
  - Registrar novos documentos com seus metadados completos
  - Consultar o histórico de documentos processados
"""

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models.database import CatalogoDocumentoORM, engine
from app.models.schema import DocumentMetadata

logger = logging.getLogger(__name__)


def compute_sha256(file_path: Path) -> str:
    """Computa o SHA-256 do conteúdo binário de um arquivo."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_sha256_from_bytes(data: bytes) -> str:
    """Computa o SHA-256 de bytes em memória (antes de salvar)."""
    return hashlib.sha256(data).hexdigest()


def is_already_processed(pdf_hash: str) -> bool:
    """
    Verifica se um documento com este hash já está no catálogo.
    Retorna True se já foi processado → pipeline ignora o arquivo.
    """
    with Session(engine) as session:
        exists = session.query(CatalogoDocumentoORM).filter_by(
            pdf_hash_sha256=pdf_hash
        ).first()
        if exists:
            logger.info(f"[CATÁLOGO] Hash {pdf_hash[:12]}... já registrado — ignorando.")
            return True
        return False


def register_document(metadata: DocumentMetadata) -> CatalogoDocumentoORM:
    """
    Registra um novo documento no catálogo.
    Deve ser chamado ANTES de processar o PDF para garantir rastreabilidade.
    """
    with Session(engine) as session:
        doc = CatalogoDocumentoORM(
            url=metadata.url,
            empresa=metadata.empresa.upper(),
            ano=metadata.ano,
            trimestre=metadata.trimestre,
            tipo_documento=metadata.tipo_documento,
            pdf_hash_sha256=metadata.pdf_hash_sha256,
            nome_arquivo=metadata.nome_arquivo,
            caminho_local=metadata.caminho_local,
            data_download=metadata.data_download,
            processado=False,
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)
        logger.info(f"[CATÁLOGO] Documento registrado: {metadata.empresa} {metadata.trimestre}T{metadata.ano}")
        return doc


def mark_as_processed(pdf_hash: str) -> None:
    """Marca um documento como processado com sucesso."""
    with Session(engine) as session:
        doc = session.query(CatalogoDocumentoORM).filter_by(
            pdf_hash_sha256=pdf_hash
        ).first()
        if doc:
            doc.processado = True
            doc.erro_processamento = None
            session.commit()


def mark_as_failed(pdf_hash: str, error: str) -> None:
    """Registra falha no processamento de um documento."""
    with Session(engine) as session:
        doc = session.query(CatalogoDocumentoORM).filter_by(
            pdf_hash_sha256=pdf_hash
        ).first()
        if doc:
            doc.processado = False
            doc.erro_processamento = error[:500]
            session.commit()
            logger.error(f"[CATÁLOGO] Falha registrada para {pdf_hash[:12]}...: {error[:100]}")


def list_catalog(empresa: Optional[str] = None, limit: int = 100) -> list:
    """Lista documentos do catálogo com filtro opcional por empresa."""
    with Session(engine) as session:
        query = session.query(CatalogoDocumentoORM)
        if empresa:
            query = query.filter_by(empresa=empresa.upper())
        return query.order_by(CatalogoDocumentoORM.data_download.desc()).limit(limit).all()
