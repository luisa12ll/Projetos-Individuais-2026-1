# Pipeline UDA — Análise de Dados Habitacionais

> **Projeto 4 — Sistemas de Machine Learning | UnB 2026/1**
>
> Pipeline de Engenharia e Análise de Dados Não Estruturados (UDA) focado no setor corporativo habitacional brasileiro, desenvolvido para alimentar o **Boletim de Conjuntura do Setor Habitacional** do Ministério das Cidades.

---

## Visão Geral da Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                    CAMADA DE COLETA                             │
│  APScheduler (1×/dia 08:00 BRT)                                 │
│  Scrapers: MRV · Direcional · Cury                              │
│  ↓ Hash SHA-256 → verifica Catálogo → evita duplicatas          │
│  ↓ Download PDF → armazenamento local organizado                │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────┐
│              CAMADA UDA — PROCESSAMENTO LLM                     │
│  PyMuPDF → Chunking Semântico Adaptativo                        │
│  ↓ Contrato Semântico (Pydantic + JSON Schema)                  │
│  ↓ Google Gemini Flash (fallback: GPT-4o-mini)                  │
│  ↓ Validação → SQLite                                           │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────┐
│              CAMADA DE SERVIÇO (FastAPI)                        │
│  GET /api/conjuntura?empresa=MRV&ano=2025&trimestre=3           │
│  GET /api/empresas · /api/catalogo · /api/health                │
│  POST /api/processar · POST /api/coletar                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Decisões Técnicas

### Estratégia de Chunking: Híbrida Adaptativa

| Condição | Estratégia | Justificativa |
|---|---|---|
| ≤ 20 páginas | **Full-Scan** | Prévias operacionais típicas têm 5-15 páginas; enviar tudo maximiza contexto e precisão |
| > 20 páginas | **Chunking Semântico** | Releases extensos: detecta headings, filtra chunks com palavras-chave operacionais, reduz custo de tokens |
| Fallback | **Full-Scan (truncado)** | Se nenhum chunk passar no filtro semântico, envia o documento até o limite de contexto |

### Motor de Extração: Nativo

- **PyMuPDF (fitz)** — parsing robusto de texto, estrutura de linhas, sem dependência de SaaS
- **Google Gemini Flash** — LLM primário (free tier generoso, alta janela de contexto)
- **OpenAI GPT-4o-mini** — fallback automático em caso de falha do Gemini

### Gatilho de Ingestão: Polling com CronJob

- **APScheduler** com timezone America/Sao_Paulo (BRT)
- Frequência: 1× por dia às 08:00 (configurável via `.env`)
- Rate limiting: mínimo de 30 segundos entre requests ao mesmo domínio

### Idempotência via SHA-256

```python
# Antes de qualquer chamada LLM:
pdf_hash = sha256(conteudo_binario_do_pdf)
if hash_ja_existe_no_catalogo(pdf_hash):
    ignorar()  # Zero custo de API
```

---

## Contrato Semântico

O `PreviaPeriodo` (Pydantic) é o núcleo de validação:

```python
class PreviaPeriodo(BaseModel):
    empresa: str                              # "MRV", "DIRECIONAL", "CURY"
    ano: int                                  # 2025
    trimestre: int                            # 1-4

    lancamentos_unidades: Optional[int]       # Valor absoluto (nunca %)
    lancamentos_vgv_milhoes: Optional[float]  # R$ milhões (nunca reais)
    vendas_liquidas_unidades: Optional[int]
    vendas_liquidas_vgv_milhoes: Optional[float]
    # ... demais métricas

    # Linhagem completa
    fonte_url: str            # URL pública do PDF
    pdf_hash_sha256: str      # SHA-256 do binário
    llm_model_usado: str      # ex: "gemini-1.5-flash"
    confianca_extracao: str   # "alta" | "media" | "baixa"
```

**Regras de blindagem contra alucinação:**
- Campos ausentes → `null` (nunca inventar valores)
- VGV sempre em R$ milhões (sanitização automática se LLM retornar em reais/bilhões)
- Empresa sempre em maiúsculas
- Trimestre validado entre 1 e 4

---

## Instalação e Configuração

### Pré-requisitos

- **Python 3.11 ou 3.12** (obrigatório — Python 3.13/3.14 ainda não tem wheels para todas as dependências)
- Pelo menos uma chave de API: Google Gemini **ou** OpenAI

> **Mac com homebrew:** `brew install python@3.11`

### 1. Criar ambiente virtual e instalar dependências

```bash
cd projeto-4/
python3.11 -m venv .venv
source .venv/bin/activate   # Linux/Mac
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite o .env com suas chaves de API:
```

```dotenv
GEMINI_API_KEY=sua_chave_gemini_aqui
# OPENAI_API_KEY=opcional_fallback
```

**Como obter a chave Gemini (gratuita):**
1. Acesse [aistudio.google.com](https://aistudio.google.com)
2. Clique em "Get API Key"
3. Cole no `.env`

---

## Execução

### Iniciar o servidor da API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Acesse a documentação interativa: **http://localhost:8000/docs**

### Processar o Boletim de Exemplo (PDF do enunciado)

```bash
# Processar PDF local
python process_example.py \
  --pdf exemplo_Boletim_Conjuntura_2025_3T.pdf \
  --empresa EXEMPLO \
  --ano 2025 \
  --trimestre 3

# Processar PDF por URL
python process_example.py \
  --url https://ri.mrv.com.br/.../previa_3t25.pdf \
  --empresa MRV \
  --ano 2025 \
  --trimestre 3
```

### Disparar coleta manual via API

```bash
# Inicia coleta de todos os portais de RI
curl -X POST http://localhost:8000/api/coletar

# Processar um PDF específico
curl -X POST http://localhost:8000/api/processar \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://ri.mrv.com.br/.../previa_3t25.pdf",
    "empresa": "MRV",
    "ano": 2025,
    "trimestre": 3
  }'
```

---

## Endpoints da API

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/health` | Status do serviço e scheduler |
| `GET` | `/api/empresas` | Empresas monitoradas com totais |
| `GET` | `/api/conjuntura` | Consulta com filtros (`empresa`, `ano`, `trimestre`) |
| `GET` | `/api/conjuntura/{empresa}` | Histórico completo de uma empresa |
| `GET` | `/api/catalogo` | Catálogo de documentos com linhagem |
| `POST` | `/api/processar` | Processa PDF por URL (dev/debug) |
| `POST` | `/api/coletar` | Dispara coleta manual imediata |

### Exemplos de consulta

```bash
# Dados da MRV no 3T25
curl "http://localhost:8000/api/conjuntura?empresa=MRV&ano=2025&trimestre=3"

# Histórico completo da Direcional
curl "http://localhost:8000/api/conjuntura/DIRECIONAL"

# Todos os dados de 2025
curl "http://localhost:8000/api/conjuntura?ano=2025"

# Linhagem de documentos
curl "http://localhost:8000/api/catalogo"
```

---

## Testes

```bash
pytest tests/ -v
```

Cobertura dos testes:
- `test_pdf_parser.py` — Parsing de PDFs reais, estratégias full-scan/chunking, detecção de conteúdo
- `test_llm_extractor.py` — Validação Pydantic, anti-alucinação, sanitização de valores, tratamento de erros
- `test_api.py` — Todos os endpoints REST com banco em memória

---

## Estrutura do Projeto

```
projeto-4/
├── README.md
├── requirements.txt
├── .env.example
├── process_example.py          # Script CLI para testes manuais
│
├── app/
│   ├── main.py                 # FastAPI + scheduler startup
│   ├── config.py               # Pydantic Settings (.env)
│   │
│   ├── models/
│   │   ├── schema.py           # Contratos Pydantic (PreviaPeriodo)
│   │   └── database.py         # SQLAlchemy ORM + SQLite
│   │
│   ├── collectors/
│   │   ├── base_collector.py   # Classe abstrata + rate limiting
│   │   ├── catalog.py          # Catálogo SHA-256 + lineage
│   │   ├── mrv_collector.py    # Scraper ri.mrv.com.br
│   │   ├── direcional_collector.py
│   │   └── cury_collector.py   # Scraper ri.cury.net
│   │
│   ├── processors/
│   │   ├── pdf_parser.py       # PyMuPDF + chunking adaptativo
│   │   ├── prompt_builder.py   # System prompt + JSON Schema
│   │   └── llm_extractor.py    # Gemini/OpenAI + validação Pydantic
│   │
│   ├── scheduler/
│   │   └── jobs.py             # APScheduler: coleta diária 08:00 BRT
│   │
│   └── api/
│       ├── schemas.py          # Schemas de resposta da API
│       └── routes.py           # FastAPI endpoints
│
├── data/
│   ├── pdfs/                   # PDFs organizados por empresa/ano/trimestre
│   └── catalog.db              # SQLite (criado automaticamente)
│
└── tests/
    ├── conftest.py
    ├── test_pdf_parser.py
    ├── test_llm_extractor.py
    └── test_api.py
```

---

## Empresas Monitoradas

| Empresa | Portal de RI | Documentos Alvo |
|---|---|---|
| MRV | [ri.mrv.com.br](https://ri.mrv.com.br) | Prévia Operacional Trimestral |
| Direcional | [ri.direcional.com.br](https://ri.direcional.com.br) | Prévia Operacional Trimestral |
| Cury | [ri.cury.net](https://ri.cury.net) | Prévia Operacional Trimestral |

Para adicionar novas empresas, crie uma subclasse de `BaseCollector` em `app/collectors/` e adicione ao `ALL_COLLECTORS` em `app/collectors/__init__.py`.

---

## Catálogo de Dados e Linhagem

Cada registro no banco contém rastreabilidade completa:

```json
{
  "empresa": "MRV",
  "periodo": "3T2025",
  "vendas_liquidas_vgv_milhoes": 2300.0,
  "fonte_url": "https://ri.mrv.com.br/central-resultados/previa_3t25.pdf",
  "pdf_hash_sha256": "a3f8c2...",
  "data_extracao": "2025-10-15T08:00:00",
  "llm_model_usado": "gemini-1.5-flash",
  "confianca_extracao": "alta"
}
```

---

## Referências Técnicas

- [PyMuPDF Documentation](https://pymupdf.readthedocs.io/)
- [Pydantic v2 Docs](https://docs.pydantic.dev/latest/)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [APScheduler Docs](https://apscheduler.readthedocs.io/)
- [Google Gemini API](https://ai.google.dev/)
