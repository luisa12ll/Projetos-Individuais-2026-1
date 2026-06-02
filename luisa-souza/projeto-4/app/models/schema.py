"""
schema.py — Contrato Semântico do Pipeline UDA

Define os modelos Pydantic que atuam como contrato de validação
entre a saída do LLM e o banco de dados. Esses schemas são também
usados na montagem do JSON Schema enviado no system prompt para
blindar o LLM contra alucinações.
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


# ── Nível de confiança da extração ──────────────────────────────────────────
ConfiancaEnum = Literal["alta", "media", "baixa"]


class PreviaPeriodo(BaseModel):
    """
    Contrato Semântico: representa os dados extraídos de uma Prévia Operacional
    ou Release de Resultados de uma incorporadora.

    Regras de Negócio:
    - Todos os campos financeiros são valores ABSOLUTOS (não %)
    - VGV sempre em MILHÕES de reais (R$ MM)
    - Se um campo não estiver no documento → None (nunca inventar)
    - trimestre: 1, 2, 3 ou 4
    """

    # ── Identificação ────────────────────────────────────────────────────────
    empresa: str = Field(..., description="Nome comercial da incorporadora (ex: 'MRV', 'Direcional', 'Cury')")
    ano: int = Field(..., ge=2020, le=2030, description="Ano fiscal do relatório (ex: 2025)")
    trimestre: int = Field(..., ge=1, le=4, description="Trimestre fiscal: 1, 2, 3 ou 4")

    # ── Lançamentos ─────────────────────────────────────────────────────────
    lancamentos_unidades: Optional[int] = Field(
        None, description="Total de unidades lançadas no trimestre (valor absoluto, não %)"
    )
    lancamentos_vgv_milhoes: Optional[float] = Field(
        None, description="VGV dos lançamentos em R$ milhões (valor absoluto)"
    )

    # ── Vendas Líquidas ──────────────────────────────────────────────────────
    vendas_liquidas_unidades: Optional[int] = Field(
        None, description="Unidades vendidas líquidas (vendas brutas - distratos)"
    )
    vendas_liquidas_vgv_milhoes: Optional[float] = Field(
        None, description="VGV das vendas líquidas em R$ milhões"
    )

    # ── Vendas Brutas ────────────────────────────────────────────────────────
    vendas_brutas_unidades: Optional[int] = Field(
        None, description="Unidades vendidas brutas no trimestre"
    )
    vendas_brutas_vgv_milhoes: Optional[float] = Field(
        None, description="VGV das vendas brutas em R$ milhões"
    )

    # ── Distratos ────────────────────────────────────────────────────────────
    distratos_unidades: Optional[int] = Field(
        None, description="Unidades distratadas no trimestre"
    )
    distratos_vgv_milhoes: Optional[float] = Field(
        None, description="VGV dos distratos em R$ milhões"
    )

    # ── Estoque ──────────────────────────────────────────────────────────────
    estoque_unidades: Optional[int] = Field(
        None, description="Unidades disponíveis em estoque ao final do trimestre"
    )
    estoque_vgv_milhoes: Optional[float] = Field(
        None, description="VGV do estoque em R$ milhões ao final do trimestre"
    )

    # ── Entregas ─────────────────────────────────────────────────────────────
    entregas_unidades: Optional[int] = Field(
        None, description="Unidades entregues (habite-se) no trimestre"
    )
    entregas_vgv_milhoes: Optional[float] = Field(
        None, description="VGV das entregas em R$ milhões"
    )

    # ── Velocidade de Vendas ─────────────────────────────────────────────────
    vsv_percentual: Optional[float] = Field(
        None, description="VSO/VSV — Velocidade de Vendas sobre Oferta em % (ex: 18.5 para 18,5%)"
    )

    # ── Metadados de Linhagem ────────────────────────────────────────────────
    fonte_url: str = Field(..., description="URL pública do PDF na Central de Resultados da empresa")
    pdf_hash_sha256: str = Field(..., description="SHA-256 do conteúdo binário do PDF")
    data_extracao: datetime = Field(default_factory=datetime.utcnow, description="Timestamp UTC da extração")
    llm_model_usado: str = Field(..., description="Identificador do modelo LLM usado (ex: 'gemini-1.5-flash')")
    confianca_extracao: Optional[ConfiancaEnum] = Field(
        None, description="Nível de confiança: 'alta' (valores claramente identificados), 'media' (inferência razoável), 'baixa' (ambíguo)"
    )
    paginas_utilizadas: Optional[str] = Field(
        None, description="Páginas do PDF usadas na extração (ex: '1-5' ou 'full')"
    )

    @field_validator("empresa")
    @classmethod
    def normalizar_empresa(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("lancamentos_vgv_milhoes", "vendas_liquidas_vgv_milhoes",
                     "vendas_brutas_vgv_milhoes", "distratos_vgv_milhoes",
                     "estoque_vgv_milhoes", "entregas_vgv_milhoes", mode="before")
    @classmethod
    def garantir_milhoes(cls, v):
        """
        Sanitiza valores em bilhões para milhões.
        Ex: Se o LLM retornar 2.76 para 'R$ 2,76 bilhões' → converte para 2760.0
        Heurística: VGV > 50.000 provavelmente está em reais → divide por 1_000_000
        """
        if v is None:
            return v
        v = float(v)
        if v > 50_000:
            return round(v / 1_000_000, 2)
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "empresa": "MRV",
                "ano": 2025,
                "trimestre": 3,
                "lancamentos_unidades": 8500,
                "lancamentos_vgv_milhoes": 2100.5,
                "vendas_liquidas_unidades": 9200,
                "vendas_liquidas_vgv_milhoes": 2300.0,
                "vendas_brutas_unidades": 9800,
                "vendas_brutas_vgv_milhoes": 2450.0,
                "distratos_unidades": 600,
                "distratos_vgv_milhoes": 150.0,
                "estoque_unidades": 12000,
                "estoque_vgv_milhoes": 3000.0,
                "entregas_unidades": 7000,
                "entregas_vgv_milhoes": 1800.0,
                "vsv_percentual": 18.5,
                "fonte_url": "https://ri.mrv.com.br/...",
                "pdf_hash_sha256": "abc123...",
                "llm_model_usado": "gemini-1.5-flash",
                "confianca_extracao": "alta",
            }
        }


class DocumentMetadata(BaseModel):
    """Metadados de linhagem para o Catálogo de Dados."""

    url: str
    empresa: str
    ano: int
    trimestre: int
    tipo_documento: str = Field(default="previa_operacional")
    pdf_hash_sha256: str
    nome_arquivo: str
    caminho_local: str
    data_download: datetime = Field(default_factory=datetime.utcnow)
    processado: bool = False
    erro_processamento: Optional[str] = None


class ConjunturaResponse(BaseModel):
    """Schema de resposta da API /api/conjuntura."""

    empresa: str
    ano: int
    trimestre: str  # "3T2025"
    lancamentos_unidades: Optional[int]
    lancamentos_vgv_milhoes: Optional[float]
    vendas_liquidas_unidades: Optional[int]
    vendas_liquidas_vgv_milhoes: Optional[float]
    vendas_brutas_unidades: Optional[int]
    vendas_brutas_vgv_milhoes: Optional[float]
    distratos_unidades: Optional[int]
    distratos_vgv_milhoes: Optional[float]
    estoque_unidades: Optional[int]
    estoque_vgv_milhoes: Optional[float]
    entregas_unidades: Optional[int]
    entregas_vgv_milhoes: Optional[float]
    vsv_percentual: Optional[float]
    fonte_url: str
    data_extracao: datetime
    confianca_extracao: Optional[str]

    class Config:
        from_attributes = True
