# Projeto Individual 4 — Pipeline UDA de Prévias Operacionais com LLM

<p align="center">
  <img src="https://img.shields.io/badge/Status-Concluído-green?style=flat-square" alt="Status">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/LLM-GPT--4o--mini-412991?style=flat-square&logo=openai&logoColor=white" alt="LLM">
  <img src="https://img.shields.io/badge/Parser-Docling-FF6B35?style=flat-square" alt="Docling">
  <img src="https://img.shields.io/badge/Playwright-Fallback_JS-2EAD33?style=flat-square&logo=playwright&logoColor=white" alt="Playwright">
  <img src="https://img.shields.io/badge/Testes-45_casos-success?style=flat-square&logo=pytest&logoColor=white" alt="Testes">
</p>

---

## Descrição

O **Pipeline UDA** é um sistema de extração automática de métricas operacionais de prévias de resultados de incorporadoras brasileiras. O pipeline coleta PDFs publicados nos portais de Relações com Investidores, extrai dados estruturados usando LLM multimodal e os expõe via API REST, transformando documentos não estruturados em dados prontos para análise.

---

## Camadas Implementadas

| Camada | Descrição | Status |
|--------|-----------|--------|
| A | Coleta automática com polling diário (APScheduler 08:00 BRT) | ✅ |
| A | Idempotência por SHA-256 - nunca reprocessa o mesmo documento | ✅ |
| A | Rate limiting (30s/domínio) e retry exponencial com tenacity | ✅ |
| A | Playwright como fallback automático para portais SPA/JavaScript | ✅ |
| A | Collectors para MRV, Cury e Direcional | ✅ |
| B | Docling como parser primário - lê tabelas rotacionadas e embaralhadas | ✅ |
| B | pdfplumber como fallback + PyMuPDF para imagens | ✅ |
| B | Estratégia adaptativa: full-scan (≤20 pág.) ou chunking semântico (>20 pág.) | ✅ |
| B | LLM multimodal (gpt-4o-mini) processa texto e imagens das páginas | ✅ |
| B | Contrato semântico Pydantic com anti-alucinação (null para campos ausentes) | ✅ |
| B | Campo `evidencias` com trecho exato do documento por valor extraído | ✅ |
| B | Sanitização automática de VGV (bilhões → milhões) | ✅ |
| C | API REST com filtros por empresa, ano e trimestre | ✅ |
| C | Catálogo com SHA-256, URL original, modelo LLM e timestamp | ✅ |
| — | 45 casos de teste com banco em memória e mocks de LLM | ✅ |

---

## Destaques Técnicos

- **Docling como motor de parsing:** Converte PDFs em Markdown estruturado usando modelos de ML, resolvendo o problema de tabelas rotacionadas (como as da MRV que o pdfplumber não consegue ler).
- **LLM Multimodal Adaptativo:** Envia texto + imagens das páginas ao gpt-4o-mini via GitHub Models (gratuito). A estratégia muda conforme a qualidade do texto extraído — texto legível usa full-text + imagens de apoio; texto embaralhado usa Docling + imagens em alta resolução.
- **Playwright como fallback:** Portais de RI que renderizam via JavaScript (SPA/React) não são acessíveis pelo BeautifulSoup. O Playwright ativa automaticamente quando nenhum PDF é encontrado no HTML estático.
- **Contrato semântico com Pydantic:** O schema `PreviaPeriodo` valida cada campo extraído, rejeita alucinações, força null para dados ausentes e inclui evidências rastreáveis por valor.

---

## Evidências de Extração

Valores validados manualmente contra os PDFs originais:

| Empresa | Período | Lançamentos (un) | Lançamentos (R$ MM) | Vendas Líq. (un) | Vendas Líq. (R$ MM) | Confiança | Parser |
|---------|---------|-----------------|---------------------|-----------------|---------------------|-----------|--------|
| MRV | 1T26 | 10.386 | 2.915 | 9.141 | 2.469 | alta | Docling (fallback — texto rotacionado) |
| Cury | 1T26 | 8.001 | 2.646,8 | 7.786 | 2.304,6 | alta | pdfplumber |
| Direcional | 1T26 | 3.109 | 1.005,8 | 4.848 | 1.582,0 | alta | pdfplumber |
| Cyrela | 3T25 | 18 | 3.411,0 | — | 2.459,0 | alta | pdfplumber + visão multimodal |

Cada extração inclui o campo `evidencias` com o trecho exato do documento:

```json
{
  "lancamentos_vgv_milhoes": "VGV (R$ milhões) | 1T26 | 2.646,8",
  "vendas_liquidas_unidades": "Número de Unidades | 1T26 | 7.786",
  "estoque_unidades": "Total (Unidades) | 1T26 | 7.373"
}
```

---

## Pré-requisitos

**1. Python 3.11**

```bash
python3.11 --version
```

**2. GitHub Personal Access Token com permissão Models**

Acesse [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens/new), crie um token com permissão **Models: Read** e guarde-o.

---

## Instalação

**1. Clone o repositório:**

```bash
git clone https://github.com/luisa12ll/Projetos-Individuais-2026-1.git
cd Projetos-Individuais-2026-1/luisa-souza/projeto-4
```

**2. Crie o ambiente virtual e instale as dependências:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

**3. Configure as variáveis de ambiente:**

```bash
cp .env.example .env
# Edite o .env e adicione seu GITHUB_TOKEN
```

O arquivo `.env` deve conter:

```env
GITHUB_TOKEN=github_pat_...
```

---

## Processando um PDF por URL

```bash
python process_example.py \
  --url 'https://api.mziq.com/mzfilemanager/v2/d/...' \
  --empresa MRV \
  --ano 2026 \
  --trimestre 1
```

Exemplo real (MRV 1T26):

```bash
python process_example.py \
  --url 'https://api.mziq.com/mzfilemanager/v2/d/4b56353d-d5d9-435f-bf63-dcbf0a6c25d5/9d9c8de1-c30a-0260-a69f-5c1c06219644?origin=2' \
  --empresa MRV --ano 2026 --trimestre 1
```

---

## Subindo a API

```bash
uvicorn app.main:app --reload
```

Acesse os endpoints:

```bash
# Todos os dados
curl "http://localhost:8000/api/conjuntura"

# Filtrar por empresa
curl "http://localhost:8000/api/conjuntura?empresa=MRV"

# Filtrar por empresa e período
curl "http://localhost:8000/api/conjuntura?empresa=CURY&ano=2026&trimestre=1"

# Catálogo de documentos processados
curl "http://localhost:8000/api/catalogo"

# Health check
curl "http://localhost:8000/api/health"
```

---

## Rodando os Testes

```bash
pytest tests/ -v
```

Resultado esperado: **45 passed**.

---

## Estrutura do Projeto

```
projeto-4/
├── app/
│   ├── api/                      # FastAPI endpoints
│   ├── collectors/
│   │   ├── base_collector.py     # Base com Playwright fallback
│   │   ├── mrv_collector.py
│   │   ├── direcional_collector.py
│   │   └── cury_collector.py
│   ├── models/
│   │   ├── database.py           # ORM SQLAlchemy
│   │   └── schema.py             # Contrato Pydantic (PreviaPeriodo)
│   ├── processors/
│   │   ├── pdf_parser.py         # Docling + pdfplumber + PyMuPDF
│   │   ├── docling_parser.py     # Fallback Docling para PDFs embaralhados
│   │   ├── llm_extractor.py      # GitHub Models multimodal adaptativo
│   │   └── prompt_builder.py     # System e user prompts
│   └── config.py
├── tests/
│   ├── test_api.py               # 18 testes de API
│   ├── test_llm_extractor.py     # 12 testes do extractor
│   └── test_pdf_parser.py        # 15 testes do parser
├── VALIDACAO.md                  # Validação manual dos valores extraídos
├── process_example.py            # Processamento por URL
├── generate_example_output.py    # Gera evidência de execução
├── exemplo_output.json           # Evidência commitada
├── requirements.txt
└── .env.example
```

---

## Tecnologias Utilizadas

- **Parser:** Docling, pdfplumber, PyMuPDF
- **LLM:** GitHub Models (gpt-4o-mini) via OpenAI SDK
- **API:** FastAPI, Uvicorn
- **Banco:** SQLite + SQLAlchemy
- **Coleta:** httpx, BeautifulSoup, Playwright
- **Validação:** Pydantic v2
- **Scheduler:** APScheduler
- **Testes:** pytest (45 casos)

---

## Autora

<div align="center"><table>
  <tr>
    <td align="center"><a href="https://github.com/luisa12ll"><img src="https://avatars.githubusercontent.com/luisa12ll" width="100px" style="border-radius: 50%;"><br/>Luísa de Souza - 232014807</a></td>
  </tr>
</table></div>