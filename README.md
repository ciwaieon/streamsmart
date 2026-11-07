# StreamSmart

**Assista ao que importa, controle o que gasta.**

O StreamSmart reúne num só lugar quanto o usuário gasta com plataformas de streaming e o que vale a pena
assistir de acordo com o tempo disponível, o humor e a companhia, priorizando o que já está nas
assinaturas que ele paga. O sistema também cruza o histórico do que foi assistido com o valor de cada
mensalidade e sugere pausar as assinaturas com baixo custo-benefício.

Projeto Integrador: Laboratório de Programação, CST em Análise e Desenvolvimento de Sistemas (UNISA).

## Tecnologias

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.10+ |
| Back-end | Flask |
| Banco de dados | SQLite (SQL puro, sem ORM) — ver `schema.sql` |
| Front-end | HTML5 + CSS3 + JavaScript (templates Jinja2), responsivo, sem dependências externas |
| Testes | pytest (31 testes) |

## Como executar

```bash
pip install -r requirements.txt
python app.py
```

Abra **http://127.0.0.1:5000** no navegador.

Usuário de demonstração (já vem com assinaturas e histórico):

- e-mail: `demo@streamsmart.com`
- senha: `demo123`

Para começar com o banco zerado, apague o arquivo `streamsmart.db`. Ele é recriado automaticamente.

### Testes e benchmark

```bash
python -m pytest          # roda os 31 testes automatizados
python benchmark.py       # compara merge sort, insertion sort e sorted(); gera resultados/benchmark.csv e .png
```

## Funcionalidades (requisitos funcionais)

| Código | Requisito | Onde está |
|---|---|---|
| RF01 | Cadastro, login e recuperação de senha (envio de e-mail simulado na tela) | `app.py` — rotas `/cadastro`, `/login`, `/recuperar`, `/redefinir` |
| RF02 | CRUD de assinaturas (plataforma, plano, valor, periodicidade, vencimento, teste grátis) | `/assinaturas`, `repositorio.py` |
| RF03 | Alertas de cobrança e de fim de teste grátis nos próximos 5 dias | `services/custos.py::alertas` (fila de prioridade) |
| RF04 | Soma mensal e projeção anual de gastos | `services/custos.py::resumo` |
| RF05 | Recomendador por tempo, vibe e companhia | `services/recomendador.py` |
| RF06 | Filtro "apenas nos streamings que eu assino" | `services/recomendador.py::pontuar` |
| RF07 | Histórico do que o usuário assistiu | `/historico` |
| RF08 | Relatório de custo-benefício com sugestão de pausa | `services/relatorio.py` |

## Estruturas de dados e algoritmos

Implementados manualmente em `services/estruturas.py`:

- **Heap binário mínimo (`MinHeap`)**: fila de prioridade que ordena os alertas pelo número de dias até o
  vencimento. Inserção e remoção em O(log n).
- **Merge sort**: ordena as recomendações por nota (decrescente) e título, e as linhas do relatório. É estável
  e roda em O(n log n).
- **Insertion sort**: O(n²), usado só no benchmark como comparação.
- **Busca binária**: O(log n).
- **Conjuntos e dicionários (tabelas hash)**: interseção entre as plataformas do título e as do usuário, e
  agrupamento do histórico por plataforma.

### Como o recomendador pontua (0 a 100)

1. **Filtros eliminatórios:** a duração precisa caber no tempo disponível (em séries, vale a duração do
   episódio), o título precisa ter a vibe escolhida, "com crianças" aceita só classificação L ou 10, e o
   filtro "só as minhas" descarta títulos fora das assinaturas do usuário.
2. **Pontuação:** vibe (35), aproveitamento do tempo (25), disponível no plano (25) e adequação à companhia
   (15). Títulos já assistidos perdem 20 pontos.
3. **Ordenação:** merge sort pela chave `(-nota, título)`.

## Estrutura de pastas

```
streamsmart/
├── app.py               # rotas Flask (controle)
├── database.py          # conexão, criação do banco e dados de demonstração
├── repositorio.py       # consultas SQL
├── schema.sql           # modelo do banco (DDL)
├── benchmark.py         # experimento de desempenho das ordenações
├── services/
│   ├── estruturas.py    # heap, merge sort, insertion sort, busca binária
│   ├── custos.py        # RF03, RF04
│   ├── recomendador.py  # RF05, RF06
│   └── relatorio.py     # RF08
├── data/catalogo.json   # catálogo de demonstração (69 títulos, 7 plataformas)
├── templates/           # telas (HTML/Jinja2)
├── static/style.css     # estilos
└── tests/               # testes automatizados (pytest)
```

## Modelo de dados

`usuarios` 1—N `assinaturas` N—1 `plataformas` · `titulos` N—N `plataformas` (tabela `titulo_plataforma`) ·
`usuarios` 1—N `historico` N—1 `titulos` · `usuarios` 1—N `tokens_recuperacao`.

## Limitações e trabalhos futuros

- O catálogo é local e de demonstração. As durações são aproximadas e a disponibilidade em cada plataforma é
  ilustrativa. Uma próxima versão pode buscar os dados na API do TMDB (The Movie Database), que traz capas,
  sinopses e as plataformas onde cada título está disponível.
- A recuperação de senha mostra o link na tela em vez de enviá-lo por e-mail.
- O histórico é registrado manualmente, porque as plataformas não oferecem API pública de histórico.
- Para colocar em produção faltam proteção CSRF nos formulários, HTTPS e uma `SECRET_KEY` definida por
  variável de ambiente.
