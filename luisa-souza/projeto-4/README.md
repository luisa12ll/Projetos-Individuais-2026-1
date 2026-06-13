🇧🇷 **Português** | 🇺🇸 [English](README-eng.md)

<h1 align="center"> Sistema de Biblioteca (SB) 📚 </h1>

<p align="center">
  <img src="https://img.shields.io/badge/Status-Concluido-green?style=flat-square" alt="Status">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Estruturas-BST%20%7C%20RBT%20%7C%20RBT--Intervalos-orange?style=flat-square" alt="Estruturas">
</p>

<p align="center">
  <img src="https://i.postimg.cc/YCsvxJLN/Captura-de-Tela-2026-04-04-a-s-02-39-39.png" width="500">
</p>

---

## 📹 Vídeo explicando o projeto
[Vídeo do YouTube](https://youtu.be/UAIRmwX32W8?si=Yz6uVB2m9AqBAE1p)

---

## 📝 Descrição

O **Sistema de Biblioteca (SB)** é uma aplicação em Python com interface em modo escuro, desenvolvida para gerenciar acervos, alunos, empréstimos e devoluções de forma eficiente.

O foco desta entrega é o **módulo de índices e busca**, implementado inteiramente sobre estruturas de árvore. Três árvores distintas foram desenvolvidas do zero e integradas ao sistema: uma **BST** para busca por ID, uma **Árvore Rubro-Negra (RBT)** que substitui a BST garantindo balanceamento, e uma **RBT de Intervalos** para detecção de conflitos de datas em empréstimos.

---

## 🌳 Estruturas de Árvore Implementadas

### 1. BST — Árvore Binária de Busca (`bst_livros.py`)

Indexa todos os livros do acervo pela numeração (ID), permitindo busca, inserção e remoção eficientes.

**Operações implementadas:**

| Operação | Complexidade | Descrição |
|----------|-------------|-----------|
| `inserir(livro)` | O(log n) médio | Insere ou atualiza um livro pelo ID |
| `buscar(numeracao)` | O(log n) médio | Busca exata por número de ID |
| `buscar_intervalo(inicio, fim)` | O(log n + k) | Retorna todos os livros em um intervalo de IDs |
| `remover(numeracao)` | O(log n) médio | Remove usando o sucessor in-order |
| `em_ordem()` | O(n) | Lista todos os livros em ordem crescente de ID |
| `construir_de_lista(livros)` | O(n log n) | Constrói a árvore a partir de uma lista |

**Limitação:** no pior caso (inserções em ordem crescente), a BST degenera em lista encadeada — O(n) por operação. Essa limitação motivou a implementação da RBT.

---

### 2. RBT — Árvore Rubro-Negra (`rbt_livros.py`)

Substitui a BST como estrutura principal de indexação de livros. Garante balanceamento automático após cada inserção e remoção, mantendo altura máxima de **2·log₂(n+1)** e custo **O(log n) garantido** em todos os casos.

**Invariantes mantidas em toda operação:**
1. A raiz é sempre **PRETA**.
2. Nenhum nó **VERMELHO** possui filho **VERMELHO**.
3. Todo caminho da raiz até uma folha NIL passa pelo mesmo número de nós **PRETOS** (altura negra uniforme).

**Estrutura do nó:**
- `numeracao` — chave de ordenação (ID do livro)
- `dados` — dicionário com todos os dados do livro
- `cor` — VERMELHO ou PRETO
- `pai`, `esq`, `dir` — ponteiros padrão + referência ao pai (necessário para rotações)
- Sentinela `_nil` compartilhada — evita verificações de `None` espalhadas no código

**Operações implementadas:**

| Operação | Complexidade | Descrição |
|----------|-------------|-----------|
| `inserir(livro)` | O(log n) | Inserção BST + `_corrigir_insercao` |
| `buscar(numeracao)` | O(log n) | Busca exata; registra número de comparações |
| `buscar_intervalo(inicio, fim)` | O(log n + k) | Retorna livros em um faixa de IDs |
| `remover(numeracao)` | O(log n) | RBT-Delete (CLRS cap. 13) + `_corrigir_remocao` |
| `em_ordem()` | O(n) | Travessia in-order; retorna livros ordenados por ID |
| `construir_de_lista(livros)` | O(n log n) | Constrói a RBT a partir de uma lista |

**Correção após inserção — 3 casos tratados (+ espelhos):**
- **Caso 1 — Tio vermelho:** recoloração do pai, tio e avô.
- **Caso 2 — Z é filho direito do pai (pai esquerdo):** rotação à esquerda no pai, reduz ao Caso 3.
- **Caso 3 — Z é filho esquerdo do pai (pai esquerdo):** rotação à direita no avô + recoloração.

**Correção após remoção — 4 casos tratados (+ espelhos), baseado em CLRS cap. 13.**

---

### 3. RBT de Intervalos (`rbt_intervalos.py`)

Extensão da RBT padrão para armazenar **intervalos de datas** de empréstimos. Cada nó representa um período `[inicio, fim]` e mantém um campo extra `max_fim` — a maior data de devolução de toda a sua subárvore. Esse campo permite **descartar ramos inteiros** durante a busca por sobreposição.

**Aplicação no sistema:** ao registrar um empréstimo, o sistema consulta a árvore para verificar se o livro já está emprestado no mesmo período, sem precisar percorrer todos os empréstimos ativos.

**Condição de sobreposição entre [a, b] e [c, d]:**
```
a ≤ d  AND  c ≤ b
```

**Estrutura do nó:**
- `inicio`, `fim` — datas do intervalo
- `max_fim` — maior `fim` de toda a subárvore (atualizado a cada rotação e inserção)
- `dados` — metadados do empréstimo
- `cor`, `pai`, `esq`, `dir` — campos padrão de RBT

**Operações implementadas:**

| Operação | Complexidade | Descrição |
|----------|-------------|-----------|
| `inserir(inicio, fim, dados)` | O(log n) | Registra um empréstimo; propaga `max_fim` até a raiz |
| `buscar_sobreposicao(inicio, fim)` | O(log n) | Retorna um empréstimo conflitante ou `None` |
| `buscar_todos_sobrepostos(inicio, fim)` | O(log n + k) | Retorna todos os conflitos; reporta nós visitados e podados |
| `remover_por_chave(chave)` | O(n) busca + O(log n) remoção | Remove o empréstimo ao registrar devolução |
| `construir_de_emprestimos(emprestimos)` | O(n log n) | Reconstrói a árvore a partir do JSON de empréstimos |

**Algoritmo de busca por sobreposição (CLRS cap. 14):**
1. Se o filho esquerdo existe e seu `max_fim ≥ inicio` buscado → desce à esquerda (conflito pode estar lá).
2. Caso contrário → desce à direita.
3. A cada nó visitado, verifica se `nó.inicio ≤ fim AND inicio ≤ nó.fim`.

---

## 🔁 Como as Árvores se Integram ao Sistema

```
Motor de Busca (motor_busca.py)
├── Consulta numérica (ID)    →  RBTBiblioteca   (rbt_livros.py)
├── Consulta textual          →  Índice Invertido (indice_invertido.py)
├── Consulta aproximada       →  BuscaAproximada  (busca_aproximada.py)
└── Conflito de empréstimo    →  RBTIntervalos    (rbt_intervalos.py)
```

A `BST` (`bst_livros.py`) permanece no projeto como estrutura base de referência — sua limitação de pior caso O(n) justifica e documenta a necessidade da RBT.

---

## 🎯 Demais Funcionalidades do Sistema

- Ordenação dinâmica da tabela por qualquer coluna (Quick Sort, Heap Sort, Radix Sort MSD)
- Cadastro e edição de livros e alunos
- Controle de empréstimos e devoluções com avaliação de 0 a 5 estrelas

---

## 💻 Pré-requisitos

- Python 3.10 ou superior
- Sistema Operacional: Windows, macOS ou Linux

## 🚀 Executando

```bash
# 1. Clonar o repositório
git clone https://github.com/eda2-2026/G41_Ordenacao_EDA2-2026.1.git

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Executar
python biblioteca.py
```

> **⚠️ Observação:** verifique se os arquivos `.json` estão presentes em `db_files/` antes de executar.

---

## 🫂 Colaboradores

| [Camila Cavalcante - 232013944](https://github.com/CamilaSilvaC) | [Luísa Ferreira - 232014807](https://github.com/luisa12ll) |
| :---: | :---: |
| <img src="https://github.com/CamilaSilvaC.png" alt="camila" width="200"> | <img src="https://github.com/luisa12ll.png" alt="luisa" width="200"> |
