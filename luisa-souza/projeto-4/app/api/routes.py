"""
routes.py — Endpoints da API REST

Contrato da API:
  GET  /api/health                     — status do serviço
  GET  /api/empresas                   — lista empresas monitoradas
  GET  /api/conjuntura                 — consulta com filtros
  GET  /api/conjuntura/{empresa}       — histórico de uma empresa
  GET  /api/catalogo                   — linhagem de documentos
  POST /api/processar                  — processa PDF manualmente (dev)
  POST /api/coletar                    — dispara coleta manual (dev)
"""

import logging
import tempfile
from datetime import datetime
from pathlib import Path
import json
from typing import Optional, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import PreviaORM, CatalogoDocumentoORM, get_session
from app.api.schemas import (
    ConjunturaResponse, EmpresaInfo, CatalogoItem,
    PipelineStatus, ProcessarRequest, ProcessarResponse
)
from app.collectors.catalog import compute_sha256_from_bytes, is_already_processed, register_document
from app.collectors.base_collector import PDFLink
from app.models.schema import DocumentMetadata
from app.processors.pdf_parser import parse_pdf
from app.processors.llm_extractor import extract_and_persist
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["conjuntura"])


# ── Helper ────────────────────────────────────────────────────────────────────

def _orm_to_response(orm: PreviaORM) -> ConjunturaResponse:
    """Converte ORM para schema de resposta."""
    return ConjunturaResponse(
        id=orm.id,
        empresa=orm.empresa,
        ano=orm.ano,
        trimestre=orm.trimestre,
        periodo=f"{orm.trimestre}T{orm.ano}",
        lancamentos_unidades=orm.lancamentos_unidades,
        lancamentos_vgv_milhoes=orm.lancamentos_vgv_milhoes,
        vendas_liquidas_unidades=orm.vendas_liquidas_unidades,
        vendas_liquidas_vgv_milhoes=orm.vendas_liquidas_vgv_milhoes,
        vendas_brutas_unidades=orm.vendas_brutas_unidades,
        vendas_brutas_vgv_milhoes=orm.vendas_brutas_vgv_milhoes,
        distratos_unidades=orm.distratos_unidades,
        distratos_vgv_milhoes=orm.distratos_vgv_milhoes,
        estoque_unidades=orm.estoque_unidades,
        estoque_vgv_milhoes=orm.estoque_vgv_milhoes,
        entregas_unidades=orm.entregas_unidades,
        entregas_vgv_milhoes=orm.entregas_vgv_milhoes,
        vsv_percentual=orm.vsv_percentual,
        fonte_url=orm.fonte_url,
        data_extracao=orm.data_extracao,
        llm_model_usado=orm.llm_model_usado,
        confianca_extracao=orm.confianca_extracao,
        evidencias=json.loads(orm.evidencias) if orm.evidencias else None,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/health", response_model=PipelineStatus, summary="Status do Pipeline")
def health_check(session: Session = Depends(get_session)):
    """Verifica o status do serviço e retorna métricas básicas."""
    from app.scheduler.jobs import scheduler

    total_previas = session.query(func.count(PreviaORM.id)).scalar()
    empresas = session.query(func.count(func.distinct(PreviaORM.empresa))).scalar()

    proximo_job = None
    try:
        job = scheduler.get_job("daily_collection")
        if job and job.next_run_time:
            proximo_job = job.next_run_time.strftime("%d/%m/%Y %H:%M BRT")
    except Exception:
        pass

    return PipelineStatus(
        status="healthy",
        version="1.0.0",
        empresas_monitoradas=empresas or 0,
        total_previas_processadas=total_previas or 0,
        scheduler_ativo=scheduler.running,
        proximo_job=proximo_job,
    )


@router.get("/empresas", response_model=List[EmpresaInfo], summary="Empresas Monitoradas")
def list_empresas(session: Session = Depends(get_session)):
    """Lista todas as incorporadoras com dados disponíveis."""
    results = (
        session.query(
            PreviaORM.empresa,
            func.count(PreviaORM.id).label("total"),
            func.max(PreviaORM.data_extracao).label("ultima"),
        )
        .group_by(PreviaORM.empresa)
        .all()
    )

    empresas = []
    for row in results:
        anos = (
            session.query(func.distinct(PreviaORM.ano))
            .filter(PreviaORM.empresa == row.empresa)
            .all()
        )
        empresas.append(EmpresaInfo(
            nome=row.empresa,
            total_previas=row.total,
            ultima_atualizacao=row.ultima,
            anos_disponiveis=sorted([a[0] for a in anos]),
        ))

    return empresas


@router.get(
    "/conjuntura",
    response_model=List[ConjunturaResponse],
    summary="Consultar Dados de Conjuntura",
)
def get_conjuntura(
    empresa: Optional[str] = Query(None, description="Nome da empresa (ex: MRV, DIRECIONAL, CURY)"),
    ano: Optional[int] = Query(None, description="Ano fiscal (ex: 2025)"),
    trimestre: Optional[int] = Query(None, ge=1, le=4, description="Trimestre: 1, 2, 3 ou 4"),
    limit: int = Query(50, ge=1, le=200, description="Máximo de resultados"),
    session: Session = Depends(get_session),
):
    """
    Consulta dados operacionais com filtros flexíveis.

    Exemplos:
    - `/api/conjuntura?empresa=MRV&ano=2025&trimestre=3`
    - `/api/conjuntura?ano=2025`
    - `/api/conjuntura?empresa=DIRECIONAL`
    """
    query = session.query(PreviaORM)

    if empresa:
        query = query.filter(PreviaORM.empresa == empresa.upper())
    if ano:
        query = query.filter(PreviaORM.ano == ano)
    if trimestre:
        query = query.filter(PreviaORM.trimestre == trimestre)

    results = (
        query
        .order_by(PreviaORM.empresa, PreviaORM.ano.desc(), PreviaORM.trimestre.desc())
        .limit(limit)
        .all()
    )

    return [_orm_to_response(r) for r in results]


@router.get(
    "/conjuntura/{empresa}",
    response_model=List[ConjunturaResponse],
    summary="Histórico Completo de uma Empresa",
)
def get_empresa_history(
    empresa: str,
    session: Session = Depends(get_session),
):
    """Retorna todo o histórico de prévias de uma empresa específica."""
    results = (
        session.query(PreviaORM)
        .filter(PreviaORM.empresa == empresa.upper())
        .order_by(PreviaORM.ano.desc(), PreviaORM.trimestre.desc())
        .all()
    )

    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"Nenhum dado encontrado para '{empresa.upper()}'. "
                   f"Empresas disponíveis: MRV, DIRECIONAL, CURY"
        )

    return [_orm_to_response(r) for r in results]


@router.get(
    "/catalogo",
    response_model=List[CatalogoItem],
    summary="Catálogo de Documentos (Linhagem)",
)
def get_catalogo(
    empresa: Optional[str] = Query(None),
    processado: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
):
    """
    Retorna o catálogo completo de documentos com rastreabilidade (data lineage).
    Cada documento inclui URL original, hash SHA-256 e status de processamento.
    """
    query = session.query(CatalogoDocumentoORM)

    if empresa:
        query = query.filter(CatalogoDocumentoORM.empresa == empresa.upper())
    if processado is not None:
        query = query.filter(CatalogoDocumentoORM.processado == processado)

    results = (
        query
        .order_by(CatalogoDocumentoORM.data_download.desc())
        .limit(limit)
        .all()
    )

    return [
        CatalogoItem(
            id=r.id,
            empresa=r.empresa,
            ano=r.ano,
            trimestre=r.trimestre,
            tipo_documento=r.tipo_documento,
            url=r.url,
            pdf_hash_sha256=r.pdf_hash_sha256,
            nome_arquivo=r.nome_arquivo,
            data_download=r.data_download,
            processado=r.processado,
            erro_processamento=r.erro_processamento,
        )
        for r in results
    ]


@router.post(
    "/processar",
    response_model=ProcessarResponse,
    summary="Processar PDF por URL (Dev/Debug)",
)
def processar_pdf_manual(
    request: ProcessarRequest,
    background_tasks: BackgroundTasks,
):
    """
    Processa um PDF diretamente por URL.
    Útil para testes e debug sem aguardar o scheduler.

    Exemplo de body:
    ```json
    {
        "url": "https://ri.mrv.com.br/.../previa_3t25.pdf",
        "empresa": "MRV",
        "ano": 2025,
        "trimestre": 3
    }
    ```
    """
    try:
        # Download do PDF
        logger.info(f"[API] Processando manualmente: {request.url}")
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(request.url)
            response.raise_for_status()
            content = response.content

        # Verificação de idempotência
        pdf_hash = compute_sha256_from_bytes(content)
        if is_already_processed(pdf_hash):
            return ProcessarResponse(
                sucesso=False,
                mensagem=f"PDF já processado anteriormente (hash: {pdf_hash[:12]}...)",
            )

        # Salva temporariamente
        dest_dir = settings.pdf_storage_dir / request.empresa.upper() / str(request.ano) / f"{request.trimestre}T"
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{request.empresa}_{request.ano}_{request.trimestre}T_{pdf_hash[:8]}.pdf"
        pdf_path = dest_dir / filename
        pdf_path.write_bytes(content)

        # Registra no catálogo
        metadata = DocumentMetadata(
            url=request.url,
            empresa=request.empresa,
            ano=request.ano,
            trimestre=request.trimestre,
            tipo_documento=request.tipo,
            pdf_hash_sha256=pdf_hash,
            nome_arquivo=filename,
            caminho_local=str(pdf_path),
        )
        register_document(metadata)

        # Parseia e extrai
        parsed = parse_pdf(pdf_path)
        if not parsed:
            return ProcessarResponse(sucesso=False, mensagem="Falha no parsing do PDF")

        previa = extract_and_persist(
            pdf_path=pdf_path,
            parsed_doc=parsed,
            empresa=request.empresa,
            ano=request.ano,
            trimestre=request.trimestre,
            fonte_url=request.url,
            pdf_hash=pdf_hash,
        )

        if not previa:
            return ProcessarResponse(sucesso=False, mensagem="Falha na extração via LLM")

        # Converte para resposta
        from sqlalchemy.orm import Session as DBSession
        from app.models.database import engine
        with DBSession(engine) as session:
            orm = session.query(PreviaORM).filter_by(pdf_hash_sha256=pdf_hash).first()
            dados = _orm_to_response(orm) if orm else None

        return ProcessarResponse(
            sucesso=True,
            mensagem=f"PDF processado com sucesso. Confiança: {previa.confianca_extracao}",
            dados=dados,
        )

    except Exception as e:
        logger.error(f"[API] Erro no processamento manual: {e}")
        return ProcessarResponse(sucesso=False, mensagem=f"Erro: {str(e)}")


@router.post("/coletar", summary="Disparar Coleta Manual (Dev)")
def trigger_collection(background_tasks: BackgroundTasks):
    """
    Dispara o pipeline de coleta imediatamente (sem aguardar o scheduler).
    Executa em background para não bloquear a resposta.
    """
    from app.scheduler.jobs import run_collection_pipeline
    background_tasks.add_task(run_collection_pipeline)
    return {
        "mensagem": "Coleta iniciada em background",
        "timestamp": datetime.utcnow().isoformat(),
    }
