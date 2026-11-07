"""
Integração com a API do The Movie Database (TMDB).

Importa filmes e séries disponíveis por assinatura no Brasil nas plataformas que o
StreamSmart conhece, com título e sinopse em português, duração, gêneros,
classificação indicativa brasileira, nota e pôster.

A disponibilidade por plataforma é fornecida ao TMDB pela JustWatch; a atribuição
às duas fontes aparece no rodapé do sistema, como exigem os termos de uso.

Usa apenas a biblioteca padrão do Python (urllib), sem dependências extras.
"""
import json
import os
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .categorias import TMDB_GENEROS, normalizar_classificacao

API = "https://api.themoviedb.org/3"
IMAGENS = "https://image.tmdb.org/t/p/w342"
REGIAO = "BR"
IDIOMA = "pt-BR"

_PLATAFORMAS_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "plataformas.json")


def _carregar_aliases():
    """Nomes como aparecem no TMDB -> nome da plataforma no StreamSmart (lidos de data/plataformas.json)."""
    with open(_PLATAFORMAS_JSON, encoding="utf-8") as f:
        plataformas = json.load(f)["plataformas"]
    return {apelido: p["nome"] for p in plataformas for apelido in p["nomes_tmdb"]}


ALIASES = _carregar_aliases()
# assinatura, grátis e grátis com anúncios (não inclui aluguel nem compra)
MONETIZACAO = "flatrate|free|ads"


class ErroTMDB(Exception):
    pass


def _normalizar(texto):
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


class ClienteTMDB:
    """Cliente mínimo da API v3. Aceita a 'chave da API' (v3) ou o 'token de leitura' (v4)."""

    def __init__(self, chave, buscar=None):
        self.chave = (chave or "").strip()
        if not self.chave:
            raise ErroTMDB("Informe a chave da API do TMDB.")
        self._buscar = buscar or self._buscar_http  # permite trocar a função nos testes

    def _buscar_http(self, url, cabecalhos):
        requisicao = urllib.request.Request(url, headers=cabecalhos)
        with urllib.request.urlopen(requisicao, timeout=20) as resposta:
            return json.loads(resposta.read().decode("utf-8"))

    def get(self, caminho, **params):
        cabecalhos = {"Accept": "application/json"}
        if self.chave.startswith("eyJ"):            # token de leitura (v4) é um JWT
            cabecalhos["Authorization"] = f"Bearer {self.chave}"
        else:
            params["api_key"] = self.chave
        url = f"{API}{caminho}?{urllib.parse.urlencode(params)}"
        for tentativa in range(4):
            try:
                return self._buscar(url, cabecalhos)
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    raise ErroTMDB("Chave do TMDB inválida. Confira se copiou a chave inteira.") from e
                if e.code == 404:
                    return None
                if e.code == 429 and tentativa < 3:          # limite de requisições: espera e tenta de novo
                    time.sleep(float(e.headers.get("Retry-After", 1)) if e.headers else 1)
                    continue
                raise ErroTMDB(f"O TMDB respondeu com erro {e.code}.") from e
            except urllib.error.URLError as e:
                if tentativa < 2:
                    time.sleep(1)
                    continue
                raise ErroTMDB("Não foi possível conectar ao TMDB. Verifique a internet.") from e
        raise ErroTMDB("O TMDB não respondeu.")

    # ------------------------------------------------------------------
    def testar(self):
        """Confere a chave fazendo uma chamada simples."""
        self.get("/configuration")
        return True

    def provedores(self):
        """Mapeia as plataformas do StreamSmart para os ids de provedor do TMDB no Brasil."""
        mapa = {}
        for tipo in ("movie", "tv"):
            dados = self.get(f"/watch/providers/{tipo}", watch_region=REGIAO, language=IDIOMA) or {}
            for p in dados.get("results", []):
                nome = ALIASES.get(_normalizar(p.get("provider_name", "")))
                if nome:
                    mapa.setdefault(nome, set()).add(p["provider_id"])
        return mapa

    def descobrir(self, tipo, provedor_id, pagina):
        return self.get(f"/discover/{tipo}", watch_region=REGIAO, with_watch_providers=provedor_id,
                        with_watch_monetization_types=MONETIZACAO, language=IDIOMA,
                        sort_by="popularity.desc", page=pagina, include_adult="false") or {}

    def detalhes(self, tipo, tmdb_id):
        extra = "release_dates" if tipo == "movie" else "content_ratings"
        return self.get(f"/{tipo}/{tmdb_id}", language=IDIOMA, append_to_response=extra)


# ---------------------------------------------------------------------- conversão
def _classificacao(tipo, detalhes):
    if tipo == "movie":
        for pais in (detalhes.get("release_dates") or {}).get("results", []):
            if pais.get("iso_3166_1") == REGIAO:
                for lancamento in pais.get("release_dates", []):
                    c = normalizar_classificacao(lancamento.get("certification"))
                    if c:
                        return c
    else:
        for pais in (detalhes.get("content_ratings") or {}).get("results", []):
            if pais.get("iso_3166_1") == REGIAO:
                return normalizar_classificacao(pais.get("rating"))
    return None


def _duracao(tipo, detalhes):
    if tipo == "movie":
        return detalhes.get("runtime") or 100
    tempos = [t for t in (detalhes.get("episode_run_time") or []) if t]
    if tempos:
        return tempos[0]
    ultimo = detalhes.get("last_episode_to_air") or {}
    return ultimo.get("runtime") or 40


def converter(tipo, detalhes, plataformas):
    """Transforma a resposta do TMDB num registro do catálogo do StreamSmart."""
    generos = []
    for g in detalhes.get("genres", []):
        for categoria in TMDB_GENEROS.get(g.get("id"), []):
            if categoria not in generos:
                generos.append(categoria)
    data = detalhes.get("release_date") if tipo == "movie" else detalhes.get("first_air_date")
    titulo = detalhes.get("title") if tipo == "movie" else detalhes.get("name")
    caminho = detalhes.get("poster_path")
    return {
        "tmdb_id": detalhes["id"],
        "tipo": "filme" if tipo == "movie" else "serie",
        "titulo": titulo or detalhes.get("original_title") or detalhes.get("original_name") or "Sem título",
        "ano": int(data[:4]) if data and data[:4].isdigit() else None,
        "duracao_min": _duracao(tipo, detalhes),
        "generos": generos,
        "classificacao": _classificacao(tipo, detalhes),
        "sinopse": (detalhes.get("overview") or "").strip() or "Sinopse ainda não disponível em português.",
        "poster_url": f"{IMAGENS}{caminho}" if caminho else None,
        "nota_tmdb": round(detalhes.get("vote_average") or 0, 1),
        "idioma_original": detalhes.get("original_language"),
        "plataformas": sorted(plataformas),
    }


# ---------------------------------------------------------------------- importação
def importar(con, cliente, paginas=3, trabalhadores=8, progresso=None):
    """Busca os títulos mais populares de cada plataforma e grava no banco.

    paginas: quantas páginas (20 títulos cada) buscar por plataforma e por tipo.
    Com 3 páginas e 7 plataformas, são até 840 títulos antes de remover repetidos.
    Devolve um resumo com a quantidade de títulos novos e atualizados.
    """
    def avisar(msg, pct=None):
        if progresso:
            progresso(msg, pct)

    ids_plataforma = {r["nome"]: r["id"] for r in con.execute("SELECT id, nome FROM plataformas")}
    provedores = cliente.provedores()
    if not provedores:
        raise ErroTMDB("Não encontrei as plataformas brasileiras no TMDB.")

    # 1) descobre os títulos de cada plataforma; um título pode aparecer em várias
    encontrados = {}  # (tipo, tmdb_id) -> conjunto de plataformas
    alvos = [(n, ids) for n, ids in provedores.items() if n in ids_plataforma]
    for i, (nome, ids) in enumerate(alvos, start=1):
        for tipo in ("movie", "tv"):
            for pagina in range(1, paginas + 1):
                dados = cliente.descobrir(tipo, "|".join(str(i) for i in sorted(ids)), pagina)
                for item in dados.get("results", []):
                    encontrados.setdefault((tipo, item["id"]), set()).add(nome)
                if pagina >= (dados.get("total_pages") or 0):
                    break
        avisar(f"Listando títulos: {nome}", round(i / len(alvos) * 20))

    # 2) busca os detalhes em paralelo (duração e classificação não vêm na lista)
    def buscar(chave):
        tipo, tmdb_id = chave
        try:
            return chave, cliente.detalhes(tipo, tmdb_id)
        except ErroTMDB:
            return chave, None

    registros = []
    chaves = list(encontrados)
    with ThreadPoolExecutor(max_workers=trabalhadores) as pool:
        for n, ((tipo, _), det) in enumerate(pool.map(buscar, chaves), start=1):
            if det:
                registros.append(converter(tipo, det, encontrados[(tipo, det["id"])]))
            if n % 50 == 0:
                avisar(f"Baixando detalhes: {n} de {len(chaves)}", 20 + round(n / len(chaves) * 70))
    avisar("Gravando no banco de dados", 92)

    # 3) grava: atualiza se já existe (pelo id do TMDB ou pelo mesmo nome e ano), senão insere
    novos = atualizados = 0
    for r in registros:
        if not r["generos"]:
            continue
        existente = con.execute("SELECT id FROM titulos WHERE tmdb_id = ? AND tipo = ?", (r["tmdb_id"], r["tipo"])).fetchone() \
            or con.execute("SELECT id FROM titulos WHERE tmdb_id IS NULL AND tipo = ? AND lower(titulo) = lower(?) AND ano = ?",
                           (r["tipo"], r["titulo"], r["ano"])).fetchone()
        valores = (r["titulo"], r["tipo"], r["ano"], r["duracao_min"], ",".join(r["generos"]), r["classificacao"],
                   r["sinopse"], r["tmdb_id"], r["poster_url"], r["nota_tmdb"], r["idioma_original"])
        if existente:
            con.execute("""UPDATE titulos SET titulo=?, tipo=?, ano=?, duracao_min=?, generos=?, classificacao=?,
                           sinopse=?, tmdb_id=?, poster_url=?, nota_tmdb=?, idioma_original=? WHERE id=?""",
                        (*valores, existente["id"]))
            tid = existente["id"]
            atualizados += 1
        else:
            tid = con.execute("""INSERT INTO titulos (titulo, tipo, ano, duracao_min, generos, classificacao, sinopse,
                                 tmdb_id, poster_url, nota_tmdb, idioma_original, vibes, origem)
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', 'tmdb')""", valores).lastrowid
            novos += 1
        # a disponibilidade vinda do catálogo oficial dos streamings tem prioridade e não é apagada
        con.execute("DELETE FROM titulo_plataforma WHERE titulo_id = ? AND (fonte IS NULL OR fonte <> 'streaming')", (tid,))
        con.executemany("INSERT OR IGNORE INTO titulo_plataforma (titulo_id, plataforma_id, fonte) VALUES (?, ?, 'tmdb')",
                        [(tid, ids_plataforma[n]) for n in r["plataformas"]])
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM titulos").fetchone()[0]
    return {"novos": novos, "atualizados": atualizados, "total": total}
