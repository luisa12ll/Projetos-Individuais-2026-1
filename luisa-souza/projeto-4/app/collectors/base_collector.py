"""
base_collector.py — Classe Abstrata Base para Collectors de RI

Define a interface que todos os scrapers específicos devem implementar.
Inclui:
  - Rate limiting via tenacity (30s mínimo entre requests ao mesmo domínio)
  - Download de PDF com verificação de hash antes de processar
  - Logging estruturado
"""

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings
from app.collectors.catalog import compute_sha256_from_bytes, is_already_processed
from app.models.schema import DocumentMetadata

logger = logging.getLogger(__name__)


class PDFLink:
    """Representa um link de PDF encontrado no portal de RI."""

    def __init__(
        self,
        url: str,
        empresa: str,
        ano: int,
        trimestre: int,
        tipo: str = "previa_operacional",
        titulo: str = "",
    ):
        self.url = url
        self.empresa = empresa
        self.ano = ano
        self.trimestre = trimestre
        self.tipo = tipo
        self.titulo = titulo

    def __repr__(self):
        return f"<PDFLink {self.empresa} {self.trimestre}T{self.ano}: {self.url[:60]}>"


class BaseCollector(ABC):
    """
    Classe base para todos os coletores de portais de RI.
    Subclasses devem implementar `get_pdf_links()`.
    """

    # Intervalo mínimo entre requests ao mesmo domínio (segundos)
    RATE_LIMIT_DELAY = settings.rate_limit_delay
    _last_request_time: dict[str, float] = {}

    def __init__(self):
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; UDA-Pipeline/1.0; "
                    "+https://github.com/ministeriodascidades/uda-pipeline)"
                )
            },
        )

    @property
    @abstractmethod
    def empresa(self) -> str:
        """Nome normalizado da empresa (ex: 'MRV')."""
        ...

    @property
    @abstractmethod
    def base_url(self) -> str:
        """URL base do portal de RI."""
        ...

    @abstractmethod
    def get_pdf_links(self) -> list[PDFLink]:
        """
        Varre o portal de RI e retorna lista de links de PDF encontrados.
        Deve filtrar apenas Prévias Operacionais e Releases de Resultados.
        """
        ...

    def _rate_limit(self, url: str) -> None:
        """Garante respeito ao rate limit por domínio."""
        domain = urlparse(url).netloc
        last = self._last_request_time.get(domain, 0)
        elapsed = time.time() - last
        if elapsed < self.RATE_LIMIT_DELAY:
            wait = self.RATE_LIMIT_DELAY - elapsed
            logger.debug(f"[RATE LIMIT] Aguardando {wait:.1f}s para {domain}")
            time.sleep(wait)
        self._last_request_time[domain] = time.time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True,
    )
    def _get(self, url: str) -> httpx.Response:
        """GET com rate limiting e retry automático."""
        self._rate_limit(url)
        response = self.client.get(url)
        response.raise_for_status()
        return response

    def download_pdf(self, pdf_link: PDFLink) -> Optional[tuple[Path, DocumentMetadata]]:
        """
        Faz o download de um PDF e:
        1. Verifica o hash SHA-256 — se já processado, retorna None
        2. Salva em disco organizado por empresa/ano/trimestre
        3. Retorna (caminho_local, DocumentMetadata) se novo

        Returns:
            Tuple[Path, DocumentMetadata] se novo documento
            None se já foi processado anteriormente
        """
        try:
            logger.info(f"[DOWNLOAD] Baixando: {pdf_link.url}")
            response = self._get(pdf_link.url)
            content = response.content

            # ── 1. Verificação de idempotência ──────────────────────────────
            pdf_hash = compute_sha256_from_bytes(content)
            if is_already_processed(pdf_hash):
                logger.info(f"[SKIP] PDF já processado: {pdf_link.url[:60]}")
                return None

            # ── 2. Salvar em disco ──────────────────────────────────────────
            dest_dir = (
                settings.pdf_storage_dir
                / pdf_link.empresa.upper()
                / str(pdf_link.ano)
                / f"{pdf_link.trimestre}T"
            )
            dest_dir.mkdir(parents=True, exist_ok=True)

            # Nome baseado no hash para evitar colisões
            filename = f"{pdf_link.empresa}_{pdf_link.ano}_{pdf_link.trimestre}T_{pdf_hash[:8]}.pdf"
            dest_path = dest_dir / filename

            dest_path.write_bytes(content)
            logger.info(f"[SALVO] {dest_path}")

            # ── 3. Montar metadados ─────────────────────────────────────────
            metadata = DocumentMetadata(
                url=pdf_link.url,
                empresa=pdf_link.empresa,
                ano=pdf_link.ano,
                trimestre=pdf_link.trimestre,
                tipo_documento=pdf_link.tipo,
                pdf_hash_sha256=pdf_hash,
                nome_arquivo=filename,
                caminho_local=str(dest_path),
            )
            return dest_path, metadata

        except Exception as e:
            logger.error(f"[ERRO] Falha no download de {pdf_link.url}: {e}")
            return None

    def collect_all(self) -> list[tuple[Path, DocumentMetadata]]:
        """
        Orquestra a coleta completa:
        1. Obtém lista de links
        2. Filtra os já processados
        3. Faz downloads dos novos
        """
        logger.info(f"[{self.empresa}] Iniciando coleta em {self.base_url}")
        try:
            links = self.get_pdf_links()
            logger.info(f"[{self.empresa}] {len(links)} link(s) encontrado(s)")
        except Exception as e:
            logger.error(f"[{self.empresa}] Falha ao obter links: {e}")
            return []

        results = []
        for link in links:
            result = self.download_pdf(link)
            if result:
                results.append(result)

        logger.info(f"[{self.empresa}] {len(results)} novo(s) PDF(s) baixado(s)")
        return results

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
