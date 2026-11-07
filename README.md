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
| Testes | pytest (54 testes) |

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
| Usuário principal (@demo) | `demo@streamsmart.com` | `demo123` |
| Amiga (@ana.souza) | `ana@streamsmart.com` | `ana12345` |
| Amigo (@brunolima) | `bruno@streamsmart.com` | `bruno123` |
| Pedido de amizade pendente (@carla.m) | `carla@streamsmart.com` | `carla123` |

Quem já tinha o `streamsmart.db` da versão anterior não precisa apagar nada: o banco é atualizado sozinho.
Para começar do zero, apague o arquivo `streamsmart.db`.

## Catálogo dos streamings (importação automática)

O catálogo é montado sozinho, em segundo plano, quando o sistema liga e a cada 6 horas. Quem usa o site não faz nada.

**Fonte principal: [Streaming Availability API](https://www.movieofthenight.com/about/api) (Movie of the Night).**
Ela lê o catálogo de cada streaming no Brasil e informa, em cada plataforma, se o título tem **áudio em português
(dublado)**, **legenda em português**, a qualidade (HD, 4K), o **link direto** para assistir e a data em que o título
sai do catálogo. O sistema pergunta à API quais streamings ela cobre no Brasil e inclui todos. Um streaming novo entra
sozinho. Os dados da API são atualizados diariamente.

**Complemento: [TMDB](https://www.themoviedb.org/).** Fornece título e sinopse em português, classificação indicativa
brasileira e duração dos episódios dos títulos acima, e cobre plataformas que a fonte principal não acompanha (nesses
casos, a tela mostra que o áudio e a legenda não foram informados pela plataforma).

**Limite do plano gratuito:** a Streaming Availability API permite 100 consultas por dia no plano gratuito, sem cartão.
O sistema controla esse limite sozinho: lê os catálogos em rodízio (primeiro a página 1 de todos os streamings, depois
a página 2...) e continua no dia seguinte de onde parou. Assim, todos os streamings aparecem desde o primeiro dia e o
catálogo vai crescendo. Com um plano pago (a partir de US$ 29 por mês), basta aumentar o limite com a variável
`STREAMING_LIMITE_DIARIO` para o catálogo completo entrar de uma vez.

**Configuração única (desenvolvedores):**

1. **Streaming Availability API:** crie a chave gratuita (pelo site da Movie of the Night ou pela RapidAPI; o sistema
   aceita as duas) e salve no arquivo `streaming_chave.txt` (modelo em `streaming_chave.exemplo.txt`).
2. **TMDB (para os textos em português):** crie uma conta em [themoviedb.org](https://www.themoviedb.org/signup), peça a
   chave em [Configurações, API](https://www.themoviedb.org/settings/api) e salve em `tmdb_chave.txt`.
3. Ligue o sistema (`python app.py`). O andamento aparece em `/catalogo`.

> ⚠️ Não envie `streaming_chave.txt`, `tmdb_chave.txt` nem `streamsmart.db` para o GitHub. Pelo terminal, o
> `.gitignore` já impede. Pelo site do GitHub, arrastando arquivos, o `.gitignore` não vale: não selecione esses arquivos.

Sem as chaves, o sistema funciona com o catálogo de demonstração (69 títulos).

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
| RF09 | Avaliação de 1 a 5 estrelas, com comentário, e registro de como assistiu (dublado ou legendado) | `/titulo/<id>`, `/avaliacoes` |
| RF10 | Nome de usuário (@), busca de pessoas, amizades (pedido, aceite, recusa) e feed com as avaliações dos amigos | `/amigos` |
| RF11 | Importação automática dos catálogos oficiais dos streamings no Brasil (Streaming Availability API), com cota diária e retomada, complementada pelo TMDB | `services/streaming.py`, `services/importador.py`, `services/tmdb.py` |
| RF12 | Dublado e legendado por plataforma (dados oficiais), link direto, qualidade e data de saída; filtros de áudio e de idioma original | `services/streaming.py`, `titulo.html` |

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
python -m pytest          # 54 testes; a integração com o TMDB é testada com respostas simuladas, sem internet
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
│   ├── streaming.py     # RF11, RF12: catálogos oficiais dos streamings, áudio e legenda
│   ├── tmdb.py          # complemento em português (TMDB)
│   └── importador.py    # importação automática em segundo plano
├── data/catalogo.json   # catálogo de demonstração (69 títulos)
├── data/plataformas.json # as 21 plataformas, cores e nomes no TMDB
├── templates/           # telas (HTML/Jinja2)
├── static/              # estilos, logo e fontes
└── tests/               # testes automatizados (pytest)
```

## Identidade visual

- Fundo grafite levemente quente, confortável para os olhos e bom para destacar pôsteres.
- Uma única cor de destaque, o Tan `#D5B893` da paleta do grupo, em botões, seleções e estrelas.
- Avisos em âmbar suave, sem vermelho.
- Cada plataforma tem um tom suave da sua família de cor: Netflix rosé `#C47F86`, Prime Video verde-azulado `#5E9E9B`,
  Disney+ azul-acinzentado `#7F98BE`, HBO Max lavanda `#A08CC4`, Globoplay âmbar `#D0A061`, Apple TV+ cinza-pedra `#A8A49C`
  e Paramount+ sálvia `#8FAE87`. O texto sobre essas cores fica claro ou escuro automaticamente, conforme o contraste.
- Classificação indicativa nas cores oficiais brasileiras, em versão suavizada.
- Tela inicial em texto corrido: o gasto do mês numa frase, até 2 avisos, sugestões para hoje à noite e um extrato
  que junta custo e uso de cada assinatura.
- Fontes Lora e Inter, ambas sob a licença SIL Open Font License, incluídas em `static/fonts`.

## Créditos e limitações

- **Dublado e legendado:** vêm do catálogo de cada streaming, pela Streaming Availability API. Para as plataformas que
  ela não cobre, vale o que os usuários informam ao registrar que assistiram (dublado ou legendado).
- Catálogos, áudios e legendas dos streamings: Streaming Availability API, da Movie of the Night (atribuição exigida
  pelos termos de uso da API, exibida no rodapé).

- Dados de filmes e séries fornecidos pelo [TMDB](https://www.themoviedb.org/). Este produto usa a API do TMDB, mas não
  é endossado nem certificado pelo TMDB. Disponibilidade nas plataformas fornecida pela [JustWatch](https://www.justwatch.com/br).
  Os termos do TMDB pedem o uso do logotipo oficial do TMDB, disponível na página de logos do próprio site.
- O catálogo de demonstração tem durações aproximadas e disponibilidade ilustrativa.
- A recuperação de senha mostra o link na tela em vez de enviá-lo por e-mail.
- O histórico é registrado manualmente, porque as plataformas não oferecem API pública de histórico.
- Para colocar em produção faltam proteção CSRF nos formulários, HTTPS e uma `SECRET_KEY` definida por variável de ambiente.
