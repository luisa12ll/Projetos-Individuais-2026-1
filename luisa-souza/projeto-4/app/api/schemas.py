"""
schemas.py — Schemas de Resposta da API FastAPI

Modelos Pydantic usados exclusivamente na camada de serviço (API).
Separados dos schemas internos para controlar a interface pública.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class ConjunturaResponse(BaseModel):
    """Dados de uma prévia operacional retornados pela API."""

    id: int
    empresa: str
    ano: int
    trimestre: int
    periodo: str  # "3T2025"

    # Lançamentos
    lancamentos_unidades: Optional[int] = None
    lancamentos_vgv_milhoes: Optional[float] = None

    # Vendas
    vendas_liquidas_unidades: Optional[int] = None
    vendas_liquidas_vgv_milhoes: Optional[float] = None
    vendas_brutas_unidades: Optional[int] = None
    vendas_brutas_vgv_milhoes: Optional[float] = None

    # Distratos
    distratos_unidades: Optional[int] = None
    distratos_vgv_milhoes: Optional[float] = None

    # Estoque
    estoque_unidades: Optional[int] = None
    estoque_vgv_milhoes: Optional[float] = None

    # Entregas
    entregas_unidades: Optional[int] = None
    entregas_vgv_milhoes: Optional[float] = None

    # VSV
    vsv_percentual: Optional[float] = None

    # Linhagem
    fonte_url: str
    data_extracao: datetime
    llm_model_usado: Optional[str] = None
    confianca_extracao: Optional[str] = None

    class Config:
        from_attributes = True


class EmpresaInfo(BaseModel):
    """Informações básicas sobre uma empresa monitorada."""
    nome: str
    total_previas: int
    ultima_atualizacao: Optional[datetime] = None
    anos_disponiveis: List[int] = []


class CatalogoItem(BaseModel):
    """Item do catálogo de documentos (linhagem)."""
    id: int
    empresa: str
    ano: int
    trimestre: int
    tipo_documento: str
    url: str
    pdf_hash_sha256: str
    nome_arquivo: Optional[str] = None
    data_download: datetime
    processado: bool
    erro_processamento: Optional[str] = None

    class Config:
        from_attributes = True


class PipelineStatus(BaseModel):
    """Status do pipeline para o endpoint /api/health."""
    status: str
    version: str
    empresas_monitoradas: int
    total_previas_processadas: int
    scheduler_ativo: bool
    proximo_job: Optional[str] = None


class ProcessarRequest(BaseModel):
    """Request para processar um PDF manualmente."""
    url: str
    empresa: str
    ano: int
    trimestre: int
    tipo: str = "previa_operacional"


class ProcessarResponse(BaseModel):
    """Resposta do processamento manual de um PDF."""
    sucesso: bool
    mensagem: str
    dados: Optional[ConjunturaResponse] = None
