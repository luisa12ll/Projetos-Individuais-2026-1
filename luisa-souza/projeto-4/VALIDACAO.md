
# Validação do Pipeline UDA — Prévias Operacionais

## Resumo

Pipeline testado com sucesso em **4 empresas** e **2 layouts distintos**, cobrindo os critérios de resiliência exigidos.

---

## Empresa 1: CURY — 1T26

**PDF:** Prévia Operacional 1T26 (15 páginas, layout slides colorido)  

**URL:** https://api.mziq.com/mzfilemanager/v2/d/702b9586-4f10-4a79-a7e6-232ce8803136/c2bd8dab-e868-3e0c-edf9-00c85e54e7df?origin=2  

**Parser:** pdfplumber (texto legível, ~5350 tokens)

| Métrica | Extraído | PDF (página 4/7) | ✅ |

|---|---|---|---|

| Lançamentos (un) | 8.001 | 8.001 | ✅ |

| Lançamentos (R$ MM) | 2.646,8 | 2.646,8 | ✅ |

| Vendas Líquidas (un) | 7.786 | 7.786 | ✅ |

| Vendas Líquidas (R$ MM) | 2.304,6 | 2.304,6 | ✅ |

| Estoque (un) | 7.373 | 7.373 | ✅ |

| Entregas (un) | 1.884 | 1.884 | ✅ |

| Confiança | alta | — | ✅ |

---

## Empresa 2: DIRECIONAL — 1T26

**PDF:** Prévia Operacional 1T26 (7 páginas, layout texto estruturado)  

**URL:** https://api.mziq.com/mzfilemanager/v2/d/ada9bc2c-f7d0-4359-9eaf-851b679ab788/b9e3e792-da8b-5e49-f50f-4c097cf08623?origin=2  

**Parser:** pdfplumber (texto legível, ~5216 tokens)

| Métrica | Extraído | PDF (página 2/3) | ✅ |

|---|---|---|---|

| Lançamentos (un) | 3.109 | 3.109 | ✅ |

| Lançamentos (R$ MM) | 1.005,8 | 1.005,8 | ✅ |

| Vendas Líquidas (un) | 4.848 | 4.848 | ✅ |

| Vendas Líquidas (R$ MM) | 1.582,0 | 1.582,0 | ✅ |

| Estoque (un) | 14.120 | 14.120 | ✅ |

| Confiança | alta | — | ✅ |

---

## Empresa 3: MRV — 1T26

**PDF:** Prévia Operacional 1T26 (13 páginas, layout slides com texto rotacionado)  

**URL:** https://api.mziq.com/mzfilemanager/v2/d/4b56353d-d5d9-435f-bf63-dcbf0a6c25d5/9d9c8de1-c30a-0260-a69f-5c1c06219644?origin=2  

**Parser:** pdfplumber falhou (1.311 tokens, texto embaralhado) → **Docling fallback** (3.072 tokens, tabela recuperada)

| Métrica | Extraído | PDF (página 7, linha TOTAL INCORPORAÇÃO) | ✅ |

|---|---|---|---|

| Lançamentos (un) | 10.386 | 10.386 | ✅ |

| Lançamentos (R$ MM) | 2.915,0 | 2.915 | ✅ |

| Vendas Líquidas (un) | 9.141 | 9.141 | ✅ |

| Vendas Líquidas (R$ MM) | 2.469,0 | 2.469 | ✅ |

| Confiança | alta | — | ✅ |

> **Nota:** O PDF da MRV usa texto rotacionado em slides, tornando o pdfplumber ineficaz. O Docling (OCR + layout analysis) recuperou a tabela corretamente, demonstrando resiliência a layouts complexos.

---

## Empresa 4: CYRELA — 3T25

**PDF:** Prévia Operacional 3T25 (8 páginas, layout misto texto + gráficos)  

**URL:** https://api.mziq.com/mzfilemanager/v2/d/d7617e78-1c42-4341-83ae-a1faa8569ca8/fe009e66-226a-1006-2f78-b36ed822f94a?origin=1  

**Parser:** pdfplumber + visão multimodal (2 imagens)

| Métrica | Extraído | PDF | ✅ |

|---|---|---|---|

| Lançamentos (un) | 18 | 18 | ✅ |

| Lançamentos (R$ MM) | 3.411,0 | 3.411 (ex-permuta) | ✅ |

| Vendas Líquidas (R$ MM) | 2.459,0 | 2.459 | ✅ |

| Confiança | alta | — | ✅ |

---



| Layout | Empresa | Estratégia de Parser |

|---|---|---|

| Texto estruturado com tabelas | Direcional, Cury | pdfplumber direto |

| Slides com texto rotacionado | MRV | pdfplumber → Docling fallback |

| Slides com dados em gráficos | Cyrela | pdfplumber + visão multimodal (PyMuPDF + gpt-4o-mini vision) |

O pipeline é **agnóstico ao layout**: detecta automaticamente a qualidade do texto extraído e escolhe a estratégia mais adequada sem configuração manual.

---



Cada PDF é identificado por seu **SHA-256** antes de ser enviado ao LLM. Re-execuções com o mesmo PDF são ignoradas automaticamente:



🔑 Hash SHA-256: a006d03645d27517180e6ccfcbb0d43ab3446741f78f2bf6c04ecf6063ea9e96[CATÁLOGO] Hash a006d036... já registrado — ignorando.



---

## API

```bash

# Todos os trimestres disponíveis

curl "http://localhost:8000/api/conjuntura"

# Filtrar por empresa

curl "http://localhost:8000/api/conjuntura?empresa=MRV"

# Filtrar por empresa e período

curl "http://localhost:8000/api/conjuntura?empresa=CURY&ano=2026&trimestre=1"

```

