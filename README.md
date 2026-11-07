# StreamSmart

**Assista ao que importa, controle o que gasta.**

O StreamSmart junta num só lugar quanto você gasta com streaming e o que vale a pena assistir agora.
Você escolhe quanto tempo tem, a vibe da sessão, as categorias, a classificação indicativa, com quem vai
assistir e em quais plataformas procurar. O sistema recomenda primeiro o que está nas assinaturas que você
já paga e avisa quando uma assinatura não está valendo o preço. Você também avalia o que assistiu, adiciona
amigos e vê as notas deles.

Projeto Integrador: Laboratório de Programação, CST em Análise e Desenvolvimento de Sistemas (UNISA).

## Tecnologias

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.10+ |
| Back-end | Flask |
| Banco de dados | SQLite (SQL puro, sem ORM), ver `schema.sql` |
| Catálogo | API do The Movie Database (TMDB), com disponibilidade por plataforma da JustWatch |
| Front-end | HTML5, CSS3 e JavaScript (templates Jinja2), responsivo, com fontes incluídas no projeto |
| Testes | pytest (44 testes) |

## Como executar

```bash
pip install -r requirements.txt
python app.py
```

Abra **http://127.0.0.1:5000** no navegador. No Windows, se `python` ou `pip` não funcionarem, use
`py app.py` e `py -m pip install -r requirements.txt`.

Contas de demonstração (já vêm com assinaturas, histórico, avaliações e amizades):

| Quem | E-mail | Senha |
|---|---|---|
| Usuário principal | `demo@streamsmart.com` | `demo123` |
| Amiga | `ana@streamsmart.com` | `ana12345` |
| Amigo | `bruno@streamsmart.com` | `bruno123` |
| Pedido de amizade pendente | `carla@streamsmart.com` | `carla123` |

Quem já tinha o `streamsmart.db` da versão anterior não precisa apagar nada: o banco é atualizado sozinho.
Para começar do zero, apague o arquivo `streamsmart.db`.

## Importar o catálogo do TMDB (milhares de títulos com pôster)

Sem o TMDB, o sistema usa um catálogo de demonstração com 69 títulos. Para importar o catálogo real:

1. Crie uma conta grátis em [themoviedb.org](https://www.themoviedb.org/signup) e confirme o e-mail.
2. Em **Configurações, API** ([themoviedb.org/settings/api](https://www.themoviedb.org/settings/api)), peça uma
   chave de uso pessoal ou educacional.
3. No StreamSmart, entre no menu **Catálogo TMDB**, cole a chave e clique em **Conferir e salvar**.
4. Escolha a quantidade e clique em **Importar do TMDB**. Na opção "Médio", leva cerca de 1 minuto.

São importados os títulos mais populares de cada plataforma, disponíveis por assinatura no Brasil, com título
e sinopse em português, pôster, duração, gêneros, classificação indicativa brasileira e nota do público. Rodar
de novo atualiza a lista e mantém o histórico e as avaliações.

## Funcionalidades (requisitos funcionais)

| Código | Requisito | Onde está |
|---|---|---|
| RF01 | Cadastro, login e recuperação de senha (envio de e-mail simulado na tela) | `app.py`, rotas `/cadastro`, `/login`, `/recuperar` |
| RF02 | Cadastro, edição e remoção de assinaturas | `/assinaturas`, `repositorio.py` |
| RF03 | Alertas de cobrança e de fim de teste grátis nos próximos 5 dias | `services/custos.py`, fila de prioridade |
| RF04 | Soma mensal e projeção anual de gastos | `services/custos.py` |
| RF05 | Recomendador com 9 opções de tempo, 12 vibes (até 3 juntas), 20 categorias, formato, companhia e classificação indicativa, com resultados paginados e 4 ordenações | `services/recomendador.py`, `services/categorias.py` |
| RF06 | Filtro por plataformas e por "só nos streamings que eu assino" | `services/recomendador.py` |
| RF07 | Histórico do que o usuário assistiu | `/historico` |
| RF08 | Relatório de custo-benefício com sugestão de pausa | `services/relatorio.py` |
| RF09 | Avaliação de 1 a 5 estrelas, com comentário, de cada título assistido | `/titulo/<id>`, `/avaliacoes` |
| RF10 | Amizades (pedido, aceite, recusa) e feed com as avaliações dos amigos | `/amigos` |
| RF11 | Importação do catálogo do TMDB | `services/tmdb.py`, `/catalogo` |

## Estruturas de dados e algoritmos

Implementados à mão em `services/estruturas.py`:

- **Heap binário mínimo (`MinHeap`)**: fila de prioridade que ordena os alertas pelos dias até o vencimento. Inserção e remoção em O(log n).
- **Merge sort**: ordena as recomendações por qualquer um dos 4 critérios e as linhas do relatório. É estável e roda em O(n log n).
- **Insertion sort**: O(n²), usado só no benchmark como comparação.
- **Busca binária**: O(log n).
- **Conjuntos e dicionários (tabelas hash)**: interseção entre as plataformas do título e as do usuário, médias das notas dos amigos por título e agrupamento do histórico.

### Como o recomendador pontua (0 a 100)

1. **Filtros eliminatórios**: formato, categorias, vibes, tempo (em séries vale a duração do episódio), classificação
   indicativa (com crianças, no máximo 10 anos), plataformas escolhidas e "só as que eu assino".
2. **Pontuação**: afinidade com a vibe (35), aproveitamento do tempo (20), disponível no plano (20), nota do público
   no TMDB (15) e companhia (10). Ganha +10 se os amigos deram nota 4 ou mais e perde 20 se você já assistiu.
3. **Ordenação**: merge sort pelo critério escolhido. São 24 títulos por página.

A afinidade de cada vibe é calculada a partir das categorias do título, com peso maior para o gênero principal.
A vibe "Bater a nostalgia" usa o ano de lançamento.

## Testes e benchmark

```bash
python -m pytest          # 44 testes; a integração com o TMDB é testada com respostas simuladas, sem internet
python benchmark.py       # compara merge sort, insertion sort e sorted(); gera resultados/benchmark.csv e .png
```

## Estrutura de pastas

```
streamsmart/
├── app.py               # rotas Flask (controle)
├── database.py          # conexão, criação/migração do banco e dados de demonstração
├── repositorio.py       # consultas SQL
├── schema.sql           # modelo do banco (DDL)
├── benchmark.py         # experimento de desempenho das ordenações
├── services/
│   ├── estruturas.py    # heap, merge sort, insertion sort, busca binária
│   ├── categorias.py    # categorias, vibes, tempos e classificação indicativa
│   ├── custos.py        # RF03, RF04
│   ├── recomendador.py  # RF05, RF06
│   ├── relatorio.py     # RF08
│   └── tmdb.py          # RF11, cliente da API do TMDB
├── data/catalogo.json   # catálogo de demonstração (69 títulos, 7 plataformas)
├── templates/           # telas (HTML/Jinja2)
├── static/              # estilos, logo e fontes
└── tests/               # testes automatizados (pytest)
```

## Identidade visual

Paleta: Space Cadet `#25344F`, Slate Gray `#617891`, Tan `#D5B893`, Coffee `#6F4D38` e Caput Mortuum `#632024`.
O conceito é uma sala de cinema: a interface é a sala escura e as informações importantes aparecem em ingressos.
Fontes Lora e Inter, ambas sob a licença SIL Open Font License, incluídas em `static/fonts`.

## Créditos e limitações

- Dados de filmes e séries fornecidos pelo [TMDB](https://www.themoviedb.org/). Este produto usa a API do TMDB, mas não
  é endossado nem certificado pelo TMDB. Disponibilidade nas plataformas fornecida pela [JustWatch](https://www.justwatch.com/br).
  Os termos do TMDB pedem o uso do logotipo oficial do TMDB, disponível na página de logos do próprio site.
- O catálogo de demonstração tem durações aproximadas e disponibilidade ilustrativa.
- A recuperação de senha mostra o link na tela em vez de enviá-lo por e-mail.
- O histórico é registrado manualmente, porque as plataformas não oferecem API pública de histórico.
- Para colocar em produção faltam proteção CSRF nos formulários, HTTPS e uma `SECRET_KEY` definida por variável de ambiente.
