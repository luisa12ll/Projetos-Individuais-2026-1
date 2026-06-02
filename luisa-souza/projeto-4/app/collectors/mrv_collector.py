"""
mrv_collector.py — Coletor do Portal de RI da MRV

Fonte: https://ri.mrv.com.br — seção Central de Resultados
Busca links de Prévias Operacionais e Releases de Resultados.
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from app.collectors.base_collector import BaseCollector, PDFLink

logger = logging.getLogger(__name__)

# Palavras-chave que identificam uma Prévia Operacional
KEYWORDS_PREVIA = [
    "prévia operacional", "previa operacional",
    "prévia", "operational preview", "previa",
]
KEYWORDS_RELEASE = [
    "release", "earnings release", "resultado", "resultado trimestral"
]


def _extrair_periodo(texto: str) -> Optional[tuple[int, int]]:
    """
    Extrai (trimestre, ano) de strings como:
    '3T25', '1T2026', 'Prévia 4T25', '2025 3T', '1T26'
    Retorna (trimestre, ano) ou None se não encontrado.
    """
    # Padrão: <T><trimestre><2 ou 4 dígitos ano>
    match = re.search(r"(\d)[Tt](\d{2,4})", texto)
    if match:
        trimestre = int(match.group(1))
        ano_raw = match.group(2)
        ano = int(ano_raw) if len(ano_raw) == 4 else 2000 + int(ano_raw)
        return trimestre, ano

    # Padrão alternativo: <ano> <T><trimestre>
    match = re.search(r"(20\d{2}).*?(\d)[Tt]", texto)
    if match:
        return int(match.group(2)), int(match.group(1))

    return None


class MRVCollector(BaseCollector):
    """Scraper do portal de RI da MRV Engenharia."""

    @property
    def empresa(self) -> str:
        return "MRV"

    @property
    def base_url(self) -> str:
        return "https://ri.mrv.com.br"

    def get_pdf_links(self) -> list[PDFLink]:
        """
        Navega na Central de Resultados da MRV e extrai links de PDF.
        Estratégia: GET na página de resultados → parseia todos os <a href="*.pdf">
        """
        pdf_links = []

        # Possíveis URLs da central de resultados MRV
        result_urls = [
            f"{self.base_url}/central-de-resultados",
            f"{self.base_url}/resultados",
            f"{self.base_url}/informacoes-financeiras/central-de-resultados",
        ]

        html_content = None
        for url in result_urls:
            try:
                response = self._get(url)
                html_content = response.text
                logger.info(f"[MRV] Página encontrada: {url}")
                break
            except Exception as e:
                logger.warning(f"[MRV] URL {url} falhou: {e}")
                continue

        if not html_content:
            logger.error("[MRV] Nenhuma URL da Central de Resultados respondeu")
            return []

        soup = BeautifulSoup(html_content, "lxml")

        # Busca todos os links que terminam em .pdf
        for tag in soup.find_all("a", href=True):
            href = tag.get("href", "")
            texto = tag.get_text(strip=True).lower()

            # Filtra apenas PDFs
            if not href.lower().endswith(".pdf"):
                # Verifica se o link aponta para um PDF mesmo sem extensão
                if "pdf" not in href.lower():
                    continue

            # Monta URL absoluta
            if href.startswith("http"):
                pdf_url = href
            elif href.startswith("/"):
                pdf_url = f"{self.base_url}{href}"
            else:
                pdf_url = f"{self.base_url}/{href}"

            # Detecta período
            periodo = _extrair_periodo(texto) or _extrair_periodo(href)
            if not periodo:
                logger.debug(f"[MRV] Link sem período identificável: {texto[:60]}")
                continue
            trimestre, ano = periodo

            # Classifica tipo do documento
            tipo = "previa_operacional"
            if any(k in texto for k in KEYWORDS_PREVIA):
                tipo = "previa_operacional"
            elif any(k in texto for k in KEYWORDS_RELEASE):
                tipo = "release_resultados"
            else:
                # Se não identificou claramente, inclui mesmo assim (pode ser útil)
                tipo = "previa_operacional"

            pdf_links.append(PDFLink(
                url=pdf_url,
                empresa=self.empresa,
                ano=ano,
                trimestre=trimestre,
                tipo=tipo,
                titulo=tag.get_text(strip=True),
            ))
            logger.debug(f"[MRV] Encontrado: {trimestre}T{ano} — {pdf_url[:60]}")

        # Remove duplicatas por URL
        seen = set()
        unique_links = []
        for link in pdf_links:
            if link.url not in seen:
                seen.add(link.url)
                unique_links.append(link)

        logger.info(f"[MRV] {len(unique_links)} PDF(s) único(s) encontrado(s)")
        return unique_links
