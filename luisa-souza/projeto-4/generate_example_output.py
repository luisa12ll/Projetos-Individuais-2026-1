"""
generate_example_output.py — Gera evidência de execução do pipeline

Processa o PDF do boletim de exemplo e salva o resultado em
exemplo_output.json para evidenciar que o pipeline funciona.

Uso:
    python generate_example_output.py
"""

import json
import logging
import sys
import hashlib
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
PDF_CANDIDATES = [
    SCRIPT_DIR / "exemplo_Boletim_Conjuntura_2025_3T.pdf",
    SCRIPT_DIR.parent / "exemplo_Boletim_Conjuntura_2025_3T.pdf",
]

def find_pdf() -> Path:
    for p in PDF_CANDIDATES:
        if p.exists():
            return p
    print("❌ PDF não encontrado. Coloque o arquivo na pasta projeto-4/")
    print("   Nome esperado: exemplo_Boletim_Conjuntura_2025_3T.pdf")
    sys.exit(1)

def compute_sha256(path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def main():
    pdf_path = find_pdf()
    print(f"✅ PDF encontrado: {pdf_path.name}")

    from app.models.database import init_db
    init_db()
    print("✅ Banco inicializado")

    pdf_hash = compute_sha256(pdf_path)
    print(f"🔑 SHA-256: {pdf_hash}")

    fonte_url = (
        "https://github.com/unb-Sistemas-de-Machine-learning/"
        "Projetos-Individuais-2026-1/blob/main/projeto-individual-4/"
        "exemplo_Boletim_Conjuntura_2025_3T.pdf"
    )

    from app.collectors.catalog import is_already_processed, register_document
    from app.models.schema import DocumentMetadata

    if not is_already_processed(pdf_hash):
        register_document(DocumentMetadata(
            url=fonte_url, empresa="BOLETIM_CONJUNTURA", ano=2025, trimestre=3,
            pdf_hash_sha256=pdf_hash, nome_arquivo=pdf_path.name,
            caminho_local=str(pdf_path.absolute()),
        ))
        print("📋 Documento registrado no catálogo")

    from app.processors.pdf_parser import parse_pdf, get_text_for_llm
    print("\n📄 Parseando PDF...")
    parsed = parse_pdf(pdf_path)
    if not parsed:
        print("❌ Falha no parsing")
        sys.exit(1)
    print(f"   Estratégia : {parsed.strategy}")
    print(f"   Páginas    : {parsed.num_pages}")
    print(f"   Tokens est : ~{parsed.estimated_tokens}")

    from app.processors.prompt_builder import build_system_prompt, build_user_prompt
    from app.processors.llm_extractor import _call_llm, _parse_llm_response

    print("\n🤖 Chamando LLM (GitHub Models - gpt-4o-mini)...")
    system_prompt = build_system_prompt("BOLETIM_CONJUNTURA", 2025, 3)
    user_prompt = build_user_prompt(get_text_for_llm(parsed), "BOLETIM_CONJUNTURA", 2025, 3)

    raw_json, model_name = _call_llm(system_prompt, user_prompt)
    if not raw_json:
        print("❌ LLM não respondeu — verifique GEMINI_API_KEY no .env")
        sys.exit(1)
    print(f"   Modelo: {model_name}")

    previa = _parse_llm_response(
        raw_json=raw_json, empresa="BOLETIM_CONJUNTURA", ano=2025, trimestre=3,
        fonte_url=fonte_url, pdf_hash=pdf_hash, model_name=model_name,
        pages_used=parsed.pages_used,
    )
    if not previa:
        print("❌ Validação Pydantic falhou")
        sys.exit(1)

    output = {
        "pipeline_run": {
            "timestamp_utc": datetime.utcnow().isoformat(),
            "pdf_fonte": pdf_path.name,
            "pdf_sha256": pdf_hash,
            "fonte_url": fonte_url,
            "llm_model": model_name,
            "estrategia_chunking": parsed.strategy,
            "paginas_processadas": parsed.pages_used,
            "tokens_estimados": parsed.estimated_tokens,
        },
        "dados_extraidos": {
            "empresa": previa.empresa,
            "ano": previa.ano,
            "trimestre": previa.trimestre,
            "periodo": f"{previa.trimestre}T{previa.ano}",
            "lancamentos_unidades": previa.lancamentos_unidades,
            "lancamentos_vgv_milhoes": previa.lancamentos_vgv_milhoes,
            "vendas_liquidas_unidades": previa.vendas_liquidas_unidades,
            "vendas_liquidas_vgv_milhoes": previa.vendas_liquidas_vgv_milhoes,
            "vendas_brutas_unidades": previa.vendas_brutas_unidades,
            "vendas_brutas_vgv_milhoes": previa.vendas_brutas_vgv_milhoes,
            "distratos_unidades": previa.distratos_unidades,
            "distratos_vgv_milhoes": previa.distratos_vgv_milhoes,
            "estoque_unidades": previa.estoque_unidades,
            "estoque_vgv_milhoes": previa.estoque_vgv_milhoes,
            "entregas_unidades": previa.entregas_unidades,
            "entregas_vgv_milhoes": previa.entregas_vgv_milhoes,
            "vsv_percentual": previa.vsv_percentual,
            "confianca_extracao": previa.confianca_extracao,
        },
        "linhagem": {
            "fonte_url": previa.fonte_url,
            "pdf_hash_sha256": previa.pdf_hash_sha256,
            "llm_model_usado": previa.llm_model_usado,
            "data_extracao": str(previa.data_extracao),
            "paginas_utilizadas": previa.paginas_utilizadas,
        },
    }

    output_path = SCRIPT_DIR / "exemplo_output.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ EXTRAÇÃO CONCLUÍDA!")
    print(f"   Confiança: {previa.confianca_extracao}")
    print(f"\n   ── Métricas extraídas ──────────────────────")
    for campo, valor in output["dados_extraidos"].items():
        if campo not in ("empresa", "ano", "trimestre", "periodo", "confianca_extracao"):
            print(f"   {campo:<40} {valor}")
    print(f"\n💾 Evidência salva em: exemplo_output.json")
    print(f"   → Commite esse arquivo no repositório!\n")

if __name__ == "__main__":
    main()
