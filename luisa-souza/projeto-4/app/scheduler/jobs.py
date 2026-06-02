"""
jobs.py — Scheduler de Coleta Automática

Usa APScheduler para rodar o pipeline de coleta diariamente às 08:00 BRT.
Cada execução:
  1. Instancia todos os collectors
  2. Coleta novos PDFs de cada portal de RI
  3. Processa com o motor UDA (PDF parser + LLM)
  4. Registra resultados no catálogo
"""

import logging
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from rich.console import Console

from app.config import settings
from app.collectors import ALL_COLLECTORS
from app.collectors.catalog import register_document, mark_as_processed, mark_as_failed
from app.processors.pdf_parser import parse_pdf
from app.processors.llm_extractor import extract_and_persist

logger = logging.getLogger(__name__)
console = Console()

# Instância global do scheduler
scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")


def run_collection_pipeline() -> dict:
    """
    Job principal: coleta e processa PDFs de todos os portais de RI.

    Returns:
        Resumo da execução: {'processados': N, 'ignorados': N, 'erros': N}
    """
    start_time = datetime.now()
    console.rule(f"[bold blue]🚀 Pipeline UDA — {start_time.strftime('%d/%m/%Y %H:%M')}")

    stats = {"processados": 0, "ignorados": 0, "erros": 0, "empresas": []}

    for CollectorClass in ALL_COLLECTORS:
        with CollectorClass() as collector:
            empresa = collector.empresa
            console.print(f"\n[bold cyan]📡 Coletando: {empresa}[/bold cyan]")

            try:
                # ── 1. Download dos PDFs novos ────────────────────────────────
                new_docs = collector.collect_all()

                if not new_docs:
                    console.print(f"  [dim]Nenhum documento novo para {empresa}[/dim]")
                    stats["ignorados"] += 1
                    continue

                empresa_stats = {"empresa": empresa, "processados": 0, "erros": 0}

                for pdf_path, metadata in new_docs:
                    console.print(
                        f"  [green]📄 Novo PDF:[/green] {metadata.nome_arquivo}"
                    )

                    try:
                        # ── 2. Registra no catálogo ───────────────────────────
                        register_document(metadata)

                        # ── 3. Parseia o PDF ──────────────────────────────────
                        parsed = parse_pdf(pdf_path)
                        if not parsed:
                            raise ValueError("Falha no parsing do PDF")

                        console.print(
                            f"    [dim]Estratégia: {parsed.strategy} | "
                            f"{parsed.num_pages} pág. | ~{parsed.estimated_tokens} tokens[/dim]"
                        )

                        # ── 4. Extrai com LLM ─────────────────────────────────
                        previa = extract_and_persist(
                            pdf_path=pdf_path,
                            parsed_doc=parsed,
                            empresa=metadata.empresa,
                            ano=metadata.ano,
                            trimestre=metadata.trimestre,
                            fonte_url=metadata.url,
                            pdf_hash=metadata.pdf_hash_sha256,
                        )

                        if previa:
                            mark_as_processed(metadata.pdf_hash_sha256)
                            stats["processados"] += 1
                            empresa_stats["processados"] += 1
                            console.print(
                                f"    [bold green]✅ Extraído:[/bold green] "
                                f"VGV Vendas={previa.vendas_liquidas_vgv_milhoes} MM | "
                                f"Confiança={previa.confianca_extracao}"
                            )
                        else:
                            raise ValueError("Extração LLM retornou None")

                    except Exception as e:
                        mark_as_failed(metadata.pdf_hash_sha256, str(e))
                        stats["erros"] += 1
                        empresa_stats["erros"] += 1
                        console.print(f"    [red]❌ Erro:[/red] {e}")

                stats["empresas"].append(empresa_stats)

            except Exception as e:
                logger.error(f"[SCHEDULER] Erro crítico em {empresa}: {e}")
                stats["erros"] += 1

    elapsed = (datetime.now() - start_time).total_seconds()
    console.rule(
        f"[bold green]✅ Pipeline concluído em {elapsed:.1f}s | "
        f"Processados: {stats['processados']} | "
        f"Erros: {stats['erros']}"
    )

    return stats


def setup_scheduler() -> BackgroundScheduler:
    """
    Configura e inicia o scheduler com o job diário.

    Job: Todo dia às HH:MM configurado no .env (padrão 08:00 BRT)
    """
    trigger = CronTrigger(
        hour=settings.scheduler_hour,
        minute=settings.scheduler_minute,
        timezone="America/Sao_Paulo",
    )

    scheduler.add_job(
        func=run_collection_pipeline,
        trigger=trigger,
        id="daily_collection",
        name="Coleta Diária de Prévias Operacionais",
        replace_existing=True,
        misfire_grace_time=3600,  # tolera até 1h de atraso
    )

    scheduler.start()
    logger.info(
        f"[SCHEDULER] Job diário configurado: "
        f"{settings.scheduler_hour:02d}:{settings.scheduler_minute:02d} BRT"
    )
    return scheduler
