"""
base_collector.py — Classe Abstrata Base para Collectors de RI

Estratégia de coleta em duas camadas:
  1. Tentativa rápida com httpx + BeautifulSoup (sem overhead, sem JS)
  2. Fallback automático com Playwright (para portais SPA/JavaScript)

O fallback é ativado automaticamente quando o BeautifulSoup
não encontra nenhum link de PDF — o sinal de que o conteúdo
é renderizado via JavaScript e não está no HTML estático.
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
    def __init__(self, url, empresa, ano, trimestre, tipo="previa_operacional", titulo=""):
        self.url = url
        self.empresa = empresa
        self.ano = ano
        self.trimestre = trimestre
        self.tipo = tipo
        self.titulo = titulo

    def __repr__(self):
        return f"<PDFLink {self.empresa} {self.trimestre}T{self.ano}: {self.url[:60]}>"


class BaseCollector(ABC):
    RATE_LIMIT_DELAY = settings.rate_limit_delay
    _last_request_time: dict[str, float] = {}

    def __init__(self):
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"},
        )

    @property
    @abstractmethod
    def empresa(self) -> str: ...

    @property
    @abstractmethod
    def base_url(self) -> str: ...

    @property
    @abstractmethod
    def result_page_urls(self) -> list[str]: ...

    @abstractmethod
    def get_pdf_links_from_html(self, html: str) -> list[PDFLink]: ...

    def _rate_limit(self, url: str) -> None:
        domain = urlparse(url).netloc
        last = self._last_request_time.get(domain, 0)
        elapsed = time.time() - last
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time[domain] = time.time()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=5, max=60),
           retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)), reraise=True)
    def _get(self, url: str) -> httpx.Response:
        self._rate_limit(url)
        response = self.client.get(url)
        response.raise_for_status()
        return response

    def _fetch_html_static(self, url: str) -> Optional[str]:
        try:
            return self._get(url).text
        except Exception as e:
            logger.warning(f"[{self.empresa}] httpx falhou em {url}: {e}")
            return None

    def _fetch_html_playwright(self, url: str) -> Optional[str]:
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
            logger.info(f"[{self.empresa}] Playwright: renderizando {url}")
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                try:
                    page.goto(url, timeout=30_000)
                    page.wait_for_load_state("networkidle", timeout=15_000)
                except PWTimeout:
                    logger.warning(f"[{self.empresa}] Playwright networkidle timeout — capturando HTML parcial")
                html = page.content()
                browser.close()
                return html
        except ImportError:
            logger.error(f"[{self.empresa}] Playwright não instalado.")
            return None
        except Exception as e:
            logger.error(f"[{self.empresa}] Playwright falhou: {e}")
            return None

    def get_pdf_links(self) -> list[PDFLink]:
        logger.info(f"[{self.empresa}] Iniciando coleta em {self.base_url}")
        all_links: list[PDFLink] = []

        # Camada 1: httpx
        for url in self.result_page_urls:
            html = self._fetch_html_static(url)
            if not html:
                continue
            links = self.get_pdf_links_from_html(html)
            if links:
                logger.info(f"[{self.empresa}] httpx: {len(links)} PDF(s) em {url}")
                all_links.extend(links)
                break
            else:
                logger.info(f"[{self.empresa}] httpx: sem PDFs em {url} — pode ser SPA")

        # Camada 2: Playwright (fallback automático)
        if not all_links:
            logger.info(f"[{self.empresa}] Ativando Playwright como fallback")
            for url in self.result_page_urls:
                html = self._fetch_html_playwright(url)
                if not html:
                    continue
                links = self.get_pdf_links_from_html(html)
                if links:
                    logger.info(f"[{self.empresa}] Playwright: {len(links)} PDF(s) em {url}")
                    all_links.extend(links)
                    break

        seen: set[str] = set()
        unique = [l for l in all_links if l.url not in seen and not seen.add(l.url)]  # type: ignore
        logger.info(f"[{self.empresa}] Total: {len(unique)} PDF(s) único(s)")
        return unique

    def download_pdf(self, pdf_link: PDFLink) -> Optional[tuple[Path, DocumentMetadata]]:
        try:
            response = self._get(pdf_link.url)
            content = response.content
            pdf_hash = compute_sha256_from_bytes(content)
            if is_already_processed(pdf_hash):
                logger.info(f"[SKIP] Já processado: {pdf_link.url[:60]}")
                return None
            dest_dir = settings.pdf_storage_dir / pdf_link.empresa.upper() / str(pdf_link.ano) / f"{pdf_link.trimestre}T"
            dest_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{pdf_link.empresa}_{pdf_link.ano}_{pdf_link.trimestre}T_{pdf_hash[:8]}.pdf"
            dest_path = dest_dir / filename
            dest_path.write_bytes(content)
            metadata = DocumentMetadata(
                url=pdf_link.url, empresa=pdf_link.empresa, ano=pdf_link.ano,
                trimestre=pdf_link.trimestre, tipo_documento=pdf_link.tipo,
                pdf_hash_sha256=pdf_hash, nome_arquivo=filename, caminho_local=str(dest_path),
            )
            return dest_path, metadata
        except Exception as e:
            logger.error(f"[ERRO] Download falhou: {e}")
            return None

    def collect_all(self) -> list[tuple[Path, DocumentMetadata]]:
        try:
            links = self.get_pdf_links()
        except Exception as e:
            logger.error(f"[{self.empresa}] Falha ao obter links: {e}")
            return []
        results = [r for link in links if (r := self.download_pdf(link))]
        logger.info(f"[{self.empresa}] {len(results)} novo(s) PDF(s) baixado(s)")
        return results

    def close(self): self.client.close()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
