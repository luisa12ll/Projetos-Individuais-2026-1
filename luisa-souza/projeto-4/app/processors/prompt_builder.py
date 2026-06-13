"""
prompt_builder.py — Construtor do System Prompt com Contrato Semântico

O prompt é o núcleo da resiliência do pipeline:
  - Define o JSON Schema exato que o LLM deve retornar
  - Instrui o modelo a extrair VALORES ABSOLUTOS (não percentuais de variação)
  - Proíbe alucinação: campos ausentes → null, nunca inventar
  - Resiliente a mudanças de layout: foco no contexto semântico, não em posição
"""

import json
from app.models.schema import PreviaPeriodo


# ── JSON Schema derivado do modelo Pydantic ──────────────────────────────────
EXTRACTION_SCHEMA = {
    "type": "object",
    "description": "Dados extraídos de uma Prévia Operacional de incorporadora brasileira",
    "required": ["empresa", "ano", "trimestre"],
    "properties": {
        "empresa": {
            "type": "string",
            "description": "Nome comercial da incorporadora (ex: 'MRV', 'DIRECIONAL', 'CURY')"
        },
        "ano": {
            "type": "integer",
            "description": "Ano fiscal do relatório (ex: 2025)"
        },
        "trimestre": {
            "type": "integer",
            "enum": [1, 2, 3, 4],
            "description": "Trimestre fiscal: 1, 2, 3 ou 4"
        },
        "lancamentos_unidades": {
            "type": ["integer", "null"],
            "description": "Total de unidades LANÇADAS no trimestre (valor absoluto)"
        },
        "lancamentos_vgv_milhoes": {
            "type": ["number", "null"],
            "description": "VGV dos lançamentos em R$ MILHÕES (ex: 2100.5 para R$ 2,1 bilhões)"
        },
        "vendas_liquidas_unidades": {
            "type": ["integer", "null"],
            "description": "Unidades VENDIDAS LÍQUIDAS (vendas brutas menos distratos)"
        },
        "vendas_liquidas_vgv_milhoes": {
            "type": ["number", "null"],
            "description": "VGV das vendas líquidas em R$ MILHÕES"
        },
        "vendas_brutas_unidades": {
            "type": ["integer", "null"],
            "description": "Unidades vendidas BRUTAS (antes de subtrair distratos)"
        },
        "vendas_brutas_vgv_milhoes": {
            "type": ["number", "null"],
            "description": "VGV das vendas brutas em R$ MILHÕES"
        },
        "distratos_unidades": {
            "type": ["integer", "null"],
            "description": "Unidades DISTRATADAS (cancelamentos) no trimestre"
        },
        "distratos_vgv_milhoes": {
            "type": ["number", "null"],
            "description": "VGV dos distratos em R$ MILHÕES"
        },
        "estoque_unidades": {
            "type": ["integer", "null"],
            "description": "Unidades disponíveis em ESTOQUE ao final do trimestre"
        },
        "estoque_vgv_milhoes": {
            "type": ["number", "null"],
            "description": "VGV do estoque em R$ MILHÕES ao final do trimestre"
        },
        "entregas_unidades": {
            "type": ["integer", "null"],
            "description": "Unidades ENTREGUES (habite-se emitido) no trimestre"
        },
        "entregas_vgv_milhoes": {
            "type": ["number", "null"],
            "description": "VGV das entregas em R$ MILHÕES"
        },
        "vsv_percentual": {
            "type": ["number", "null"],
            "description": "VSO/VSV — Velocidade de Vendas sobre Oferta em PERCENTUAL (ex: 18.5 para 18,5%)"
        },
        "confianca_extracao": {
            "type": ["string", "null"],
            "enum": ["alta", "media", "baixa", None],
            "description": "Nível de confiança: 'alta'=valores claramente identificados, 'media'=inferência razoável, 'baixa'=ambíguo"
        }
    }
}

SYSTEM_PROMPT_TEMPLATE = """Você é um analista especialista em dados do setor imobiliário brasileiro, contratado pelo Ministério das Cidades para extrair métricas operacionais de prévias e relatórios trimestrais de incorporadoras.

## TAREFA
Extraia as métricas operacionais do documento PDF a seguir e retorne um JSON válido seguindo RIGOROSAMENTE o schema abaixo.

## REGRAS CRÍTICAS — LEIA COM ATENÇÃO

### 1. VALORES ABSOLUTOS, NUNCA PERCENTUAIS
- As incorporadoras frequentemente destacam variações percentuais no marketing (ex: "↑23% nas vendas")
- IGNORE completamente todos os percentuais de variação, crescimento ou queda
- Extraia APENAS valores absolutos: número de unidades (inteiro) e VGV em R$ milhões (decimal)

### 2. UNIDADE MONETÁRIA — R$ MILHÕES
- Todos os campos de VGV devem ser em R$ MILHÕES
- Se o documento apresentar em bilhões: multiplique por 1000 (ex: R$ 2,76 bilhões → 2760.0)
- Se o documento apresentar em reais: divida por 1.000.000
- Sempre use ponto como separador decimal no JSON

### 3. VALORES AUSENTES → null (NUNCA INVENTE)
- Se uma métrica não aparecer claramente no documento, retorne null
- NUNCA deduza ou calcule valores que não estejam explicitamente no texto
- NUNCA repita o mesmo valor em campos diferentes apenas para preencher

### 4. IDENTIFICAÇÃO DO PERÍODO
- Identifique corretamente o ano e trimestre do RELATÓRIO (não da data de publicação)
- Exemplo: "Prévia 3T25" → ano=2025, trimestre=3

### 5. VENDAS LÍQUIDAS vs BRUTAS
- Vendas Brutas = total de contratos assinados
- Distratos = cancelamentos
- Vendas Líquidas = Vendas Brutas − Distratos
- Se só encontrar "Vendas" sem qualificador → assuma Vendas Líquidas

### 6. RESILIÊNCIA A LAYOUTS
- O documento pode estar em formato de tabela, slides, bullet points ou texto corrido
- Não dependa da posição visual — use o CONTEXTO SEMÂNTICO das palavras

## JSON SCHEMA OBRIGATÓRIO
```json
{schema}
```

## FORMATO DE RESPOSTA
Retorne APENAS o JSON, sem markdown, sem explicações, sem texto adicional.
Comece sua resposta diretamente com `{{` e termine com `}}`.
"""


def build_system_prompt(empresa: str, ano: int, trimestre: int) -> str:
    """
    Monta o system prompt completo com o contrato semântico embutido.

    Args:
        empresa: Nome da empresa para contextualizar o modelo
        ano: Ano esperado do relatório
        trimestre: Trimestre esperado
    """
    schema_json = json.dumps(EXTRACTION_SCHEMA, ensure_ascii=False, indent=2)
    return SYSTEM_PROMPT_TEMPLATE.format(schema=schema_json)


def build_user_prompt(document_text: str, empresa: str, ano: int, trimestre: int) -> str:
    """
    Monta o prompt do usuário com o texto do documento.

    Args:
        document_text: Texto extraído do PDF (full-scan ou chunks concatenados)
        empresa: Nome da empresa
        ano: Ano esperado
        trimestre: Trimestre esperado
    """
    return f"""## DOCUMENTO A ANALISAR

**Empresa esperada:** {empresa}
**Período esperado:** {trimestre}T{ano}

---

{document_text}

---

Extraia as métricas operacionais deste documento e retorne o JSON conforme o schema especificado.
Inclua também o campo "evidencias" com o trecho exato do documento de onde cada valor foi extraído.
Exemplo de evidencias: lancamentos_vgv_milhoes -> "VGV (R$ milhoes) | TOTAL INCORPORACAO | 2.915"
Lembre-se: valores ausentes → null. Nunca invente dados.
ATENÇÃO 1: Se a tabela tiver múltiplas linhas (ex: MRV, Sensia, Total Incorporação; ou Direcional, Riva, Total),
extraia SEMPRE os valores da linha TOTAL ou TOTAL INCORPORAÇÃO, nunca de linhas individuais.
ATENÇÃO 2: Se a tabela tiver múltiplas colunas de períodos (ex: 1T26, 4T25, 1T25), extraia SEMPRE os valores da coluna do PERÍODO MAIS RECENTE da tabela, que é o período do relatório.
ATENÇÃO 3: IGNORE completamente valores de geração de caixa, venda de ativos, Resia, Urba, Luggo ou operações nos EUA. Extraia APENAS métricas operacionais de LANÇAMENTOS e VENDAS de imóveis no Brasil (unidades e VGV).
ATENÇÃO 4: Os dados corretos estão nas IMAGENS anexadas, não no texto. Priorize as imagens para extrair os valores da tabela INDICADORES OPERACIONAIS."""

# Instrução adicional injetada no user prompt para empresas com múltiplas linhas
MULTI_LINE_INSTRUCTION = """
ATENÇÃO ESPECIAL: Se a tabela tiver múltiplas linhas (ex: MRV, Sensia, Total Incorporação),
extraia SEMPRE os valores da linha TOTAL ou TOTAL INCORPORAÇÃO, nunca de linhas individuais.
"""
