"""
direcional_collector.py — Coletor do Portal de RI da Direcional Engenharia

Fonte: https://ri.direcional.com.br — seção Central de Resultados
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from app.collectors.base_collector import BaseCollector, PDFLink

logger = logging.getLogger(__name__)


def _extrair_periodo(texto: str) -> Optional[tuple[int, int]]:
    """Extrai (trimestre, ano) de texto livre."""
    match = re.search(r"(\d)[Tt](\d{2,4})", texto)
    if match:
        trimestre = int(match.group(1))
        ano_raw = match.group(2)
        ano = int(ano_raw) if len(ano_raw) == 4 else 2000 + int(ano_raw)
        return trimestre, ano
    match = re.search(r"(20\d{2}).*?(\d)[Tt]", texto)
    if match:
        return int(match.group(2)), int(match.group(1))
    return None


class DirecionalCollector(BaseCollector):
    """Scraper do portal de RI da Direcional Engenharia."""

    @property
    def empresa(self) -> str:
        return "DIRECIONAL"

    @property
    def base_url(self) -> str:
        return "https://ri.direcional.com.br"

    def get_pdf_links(self) -> list[PDFLink]:
        """
        Navega na Central de Resultados da Direcional.
        Caminho: Informações Financeiras → Central de Resultados
        """
        pdf_links = []

        result_urls = [
            f"{self.base_url}/central-de-resultados",
            f"{self.base_url}/informacoes-financeiras/central-de-resultados",
            f"{self.base_url}/resultados",
        ]

        html_content = None
        for url in result_urls:
            try:
                response = self._get(url)
                html_content = response.text
                logger.info(f"[DIRECIONAL] Página encontrada: {url}")
                break
            except Exception as e:
                logger.warning(f"[DIRECIONAL] URL {url} falhou: {e}")

        if not html_content:
            logger.error("[DIRECIONAL] Nenhuma URL respondeu")
            return []

        soup = BeautifulSoup(html_content, "lxml")

        for tag in soup.find_all("a", href=True):
            href = tag.get("href", "")
            texto = tag.get_text(strip=True).lower()

            if ".pdf" not in href.lower() and "pdf" not in href.lower():
                continue

            if href.startswith("http"):
                pdf_url = href
            elif href.startswith("/"):
                pdf_url = f"{self.base_url}{href}"
            else:
                pdf_url = f"{self.base_url}/{href}"

            periodo = _extrair_periodo(texto) or _extrair_periodo(href)
            if not periodo:
                continue
            trimestre, ano = periodo

            tipo = "previa_operacional"
            if any(k in texto for k in ["release", "resultado"]):
                tipo = "release_resultados"

            pdf_links.append(PDFLink(
                url=pdf_url,
                empresa=self.empresa,
                ano=ano,
                trimestre=trimestre,
                tipo=tipo,
                titulo=tag.get_text(strip=True),
            ))

        seen = set()
        unique_links = [
            link for link in pdf_links
            if link.url not in seen and not seen.add(link.url)
        ]

        logger.info(f"[DIRECIONAL] {len(unique_links)} PDF(s) encontrado(s)")
        return unique_links
