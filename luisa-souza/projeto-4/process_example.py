"""
Script de processamento do Boletim de Exemplo

Executa o pipeline completo sobre o PDF do boletim de conjuntura
fornecido pelo enunciado (exemplo_Boletim_Conjuntura_2025_3T.pdf).

Uso:
    python process_example.py --pdf ../exemplo_Boletim_Conjuntura_2025_3T.pdf

Ou com URL direta:
    python process_example.py --url https://...
"""

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

def main():
    parser = argparse.ArgumentParser(description="Processa um PDF de Prévia Operacional")
    parser.add_argument("--pdf", type=Path, help="Caminho local do PDF")
    parser.add_argument("--url", type=str, help="URL do PDF")
    parser.add_argument("--empresa", type=str, default="EXEMPLO", help="Nome da empresa")
    parser.add_argument("--ano", type=int, default=2025, help="Ano do relatório")
    parser.add_argument("--trimestre", type=int, default=3, help="Trimestre (1-4)")
    args = parser.parse_args()

    if not args.pdf and not args.url:
        print("❌ Informe --pdf ou --url")
        sys.exit(1)

    # Inicializa banco
    from app.models.database import init_db
    init_db()
    print("✅ Banco inicializado")

    pdf_path = None

    if args.url:
        import httpx
        from app.config import settings
        from app.collectors.catalog import compute_sha256_from_bytes, is_already_processed
        from app.collectors.catalog import register_document
        from app.models.schema import DocumentMetadata

        print(f"📡 Baixando PDF: {args.url}")
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.get(args.url)
            response.raise_for_status()
            content = response.content

        pdf_hash = compute_sha256_from_bytes(content)
        print(f"🔑 Hash SHA-256: {pdf_hash}")

        if is_already_processed(pdf_hash):
            print("⚠️  PDF já foi processado anteriormente (hash já registrado).")
            sys.exit(0)

        dest = settings.pdf_storage_dir / args.empresa / str(args.ano) / f"{args.trimestre}T"
        dest.mkdir(parents=True, exist_ok=True)
        filename = f"{args.empresa}_{args.ano}_{args.trimestre}T_{pdf_hash[:8]}.pdf"
        pdf_path = dest / filename
        pdf_path.write_bytes(content)
        print(f"💾 Salvo em: {pdf_path}")

        metadata = DocumentMetadata(
            url=args.url,
            empresa=args.empresa,
            ano=args.ano,
            trimestre=args.trimestre,
            pdf_hash_sha256=pdf_hash,
            nome_arquivo=filename,
            caminho_local=str(pdf_path),
        )
        register_document(metadata)
        fonte_url = args.url

    else:
        pdf_path = args.pdf
        if not pdf_path.exists():
            print(f"❌ Arquivo não encontrado: {pdf_path}")
            sys.exit(1)

        from app.collectors.catalog import compute_sha256, is_already_processed, register_document
        from app.models.schema import DocumentMetadata

        pdf_hash = compute_sha256(pdf_path)
        print(f"🔑 Hash SHA-256: {pdf_hash}")

        if is_already_processed(pdf_hash):
            print("⚠️  PDF já foi processado anteriormente.")
            sys.exit(0)

        fonte_url = f"file://{pdf_path.absolute()}"
        metadata = DocumentMetadata(
            url=fonte_url,
            empresa=args.empresa,
            ano=args.ano,
            trimestre=args.trimestre,
            pdf_hash_sha256=pdf_hash,
            nome_arquivo=pdf_path.name,
            caminho_local=str(pdf_path),
        )
        register_document(metadata)

    # Parseia
    from app.processors.pdf_parser import parse_pdf
    print(f"\n📄 Parseando PDF...")
    parsed = parse_pdf(pdf_path)
    if not parsed:
        print("❌ Falha no parsing")
        sys.exit(1)

    print(f"   Estratégia: {parsed.strategy}")
    print(f"   Páginas: {parsed.num_pages}")
    print(f"   Tokens estimados: {parsed.estimated_tokens}")
    print(f"   Chunks relevantes: {len(parsed.chunks)}")

    # Extrai
    from app.processors.llm_extractor import extract_and_persist
    print(f"\n🤖 Extraindo via LLM...")
    previa = extract_and_persist(
        pdf_path=pdf_path,
        parsed_doc=parsed,
        empresa=args.empresa,
        ano=args.ano,
        trimestre=args.trimestre,
        fonte_url=fonte_url,
        pdf_hash=pdf_hash,
    )

    if previa:
        print(f"\n✅ EXTRAÇÃO CONCLUÍDA!")
        print(f"   Empresa: {previa.empresa}")
        print(f"   Período: {previa.trimestre}T{previa.ano}")
        print(f"   Confiança: {previa.confianca_extracao}")
        print(f"\n   --- MÉTRICAS EXTRAÍDAS ---")
        print(f"   Lançamentos (un): {previa.lancamentos_unidades}")
        print(f"   Lançamentos (R$ MM): {previa.lancamentos_vgv_milhoes}")
        print(f"   Vendas Líquidas (un): {previa.vendas_liquidas_unidades}")
        print(f"   Vendas Líquidas (R$ MM): {previa.vendas_liquidas_vgv_milhoes}")
        print(f"   Estoque (un): {previa.estoque_unidades}")
        print(f"   Entregas (un): {previa.entregas_unidades}")
        print(f"   VSV: {previa.vsv_percentual}%")
        print(f"\n   LLM usado: {previa.llm_model_usado}")
        print(f"   Páginas: {previa.paginas_utilizadas}")
    else:
        print("❌ Falha na extração")
        sys.exit(1)


if __name__ == "__main__":
    main()
