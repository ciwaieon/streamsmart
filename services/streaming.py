"""
Catálogo dos streamings no Brasil via Streaming Availability API (Movie of the Night).

É a fonte principal do StreamSmart: para cada streaming disponível no Brasil, traz os
títulos do catálogo e, em cada plataforma, os idiomas de áudio e de legenda (dublado /
legendado em português), a qualidade, o link direto e a data em que o título sai.

O TMDB entra só como complemento (título e sinopse em português, classificação
indicativa brasileira e duração dos episódios), usando o id do TMDB que a própria API informa.

Plano gratuito: 100 consultas por dia. O importador respeita esse limite e continua de
onde parou no dia seguinte (os cursores de paginação ficam salvos no banco).
"""
import json
import os
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

from .categorias import normalizar_generos

PAIS = "br"
HOSTS = [
    # (nome, endereço base, cabeçalhos de autenticação)
    ("direto", "https://api.movieofthenight.com/v4", lambda chave: {"X-API-Key": chave}),
    ("rapidapi", "https://streaming-availability.p.rapidapi.com",
     lambda chave: {"X-RapidAPI-Key": chave, "X-RapidAPI-Host": "streaming-availability.p.rapidapi.com"}),
]
IDIOMA_PT = "por"   # ISO 639-2

# gêneros da API -> categorias do StreamSmart
GENEROS = {
    "action": "ação", "adventure": "aventura", "animation": "animação", "comedy": "comédia", "crime": "crime",
    "documentary": "documentário", "drama": "drama", "family": "família", "fantasy": "fantasia", "history": "história",
    "horror": "terror", "music": "musical", "mystery": "mistério", "reality": "reality", "romance": "romance",
    "scifi": "ficção científica", "thriller": "suspense", "war": "guerra", "western": "faroeste", "news": "documentário",
    "talk": "reality",
}

_PLATAFORMAS_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "plataformas.json")


class ErroStreaming(Exception):
    pass


class CotaEsgotada(ErroStreaming):
    pass


def _normalizar(texto):
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return "".join(c for c in sem_acento.lower() if c.isalnum())


class ClienteStreaming:
    """Cliente da API v4. Funciona com a chave do site da Movie of the Night ou com a chave da RapidAPI."""

    def __init__(self, chave, buscar=None):
        self.chave = (chave or "").strip()
        if not self.chave:
            raise ErroStreaming("Informe a chave da Streaming Availability API.")
        self._buscar = buscar or self._buscar_http
        self._host = 0
        self.requisicoes = 0

    def _buscar_http(self, url, cabecalhos):
        requisicao = urllib.request.Request(url, headers={**cabecalhos, "Accept": "application/json"})
        with urllib.request.urlopen(requisicao, timeout=30) as resposta:
            return json.loads(resposta.read().decode("utf-8"))

    def get(self, caminho, **params):
        params = {k: v for k, v in params.items() if v not in (None, "")}
        tentou_outro_host = False
        for tentativa in range(4):
            _, base, cabecalhos = HOSTS[self._host]
            url = f"{base}{caminho}?{urllib.parse.urlencode(params)}"
            try:
                self.requisicoes += 1
                return self._buscar(url, cabecalhos(self.chave))
            except urllib.error.HTTPError as e:
                if e.code in (401, 403) and not tentou_outro_host:
                    self._host = 1 - self._host            # a chave pode ser da RapidAPI: troca de servidor
                    tentou_outro_host = True
                    continue
                if e.code in (401, 403):
                    raise ErroStreaming("Chave da Streaming Availability API inválida.") from e
                if e.code == 404:
                    return None
                if e.code == 429:
                    raise CotaEsgotada("Limite diário de consultas da Streaming Availability API atingido.") from e
                if e.code >= 500 and tentativa < 3:
                    time.sleep(2)
                    continue
                raise ErroStreaming(f"A Streaming Availability API respondeu com erro {e.code}.") from e
            except urllib.error.URLError as e:
                if tentativa < 2:
                    time.sleep(2)
                    continue
                raise ErroStreaming("Não foi possível conectar à Streaming Availability API.") from e
        raise ErroStreaming("A Streaming Availability API não respondeu.")

    def servicos(self):
        """Streamings que a API acompanha no Brasil (ordenados por popularidade)."""
        dados = self.get(f"/countries/{PAIS}", output_language="en") or {}
        return dados.get("services", [])

    def catalogo(self, catalogo, tipo, cursor=None):
        """Uma página do catálogo de um streaming. tipo: 'movie' ou 'series'."""
        return self.get("/shows/search/filters", country=PAIS, catalogs=catalogo, show_type=tipo,
                        order_by="popularity_1year", output_language="en", cursor=cursor) or {}


# ---------------------------------------------------------------------- plataformas
def carregar_mapa_plataformas():
    """id do serviço na API -> nome da plataforma no StreamSmart (de data/plataformas.json)."""
    with open(_PLATAFORMAS_JSON, encoding="utf-8") as f:
        plataformas = json.load(f)["plataformas"]
    mapa = {}
    for p in plataformas:
        for i in p.get("ids_streaming", []):
            mapa[i] = p["nome"]
        mapa[_normalizar(p["nome"])] = p["nome"]
    return mapa


def _cor_suave(hex_cor):
    """Suaviza a cor da marca (mistura com cinza) para combinar com a paleta do sistema."""
    try:
        r, g, b = (int(hex_cor.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, AttributeError):
        return "#A8A49C"
    cinza = 150
    return "#{:02X}{:02X}{:02X}".format(*(round(c * .55 + cinza * .45) for c in (r, g, b)))


def sincronizar_plataformas(con, servicos):
    """Garante que todo streaming coberto no Brasil exista na tabela de plataformas.

    Devolve a lista de catálogos a consultar: [(id_servico, catalogo, nome_plataforma)].
    """
    mapa = carregar_mapa_plataformas()
    alvos = []
    for s in servicos:
        tipos = s.get("streamingOptionTypes") or {}
        if not (tipos.get("subscription") or tipos.get("free")):
            continue                                       # lojas de aluguel/compra não entram
        nome = mapa.get(s["id"]) or mapa.get(_normalizar(s.get("name")))
        if not nome:  # streaming novo: entra sozinho, com a cor da marca suavizada
            nome = s.get("name") or s["id"]
            con.execute("INSERT OR IGNORE INTO plataformas (nome, cor) VALUES (?, ?)",
                        (nome, _cor_suave(s.get("themeColorCode", "#A8A49C"))))
        if tipos.get("subscription"):
            alvos.append((s["id"], f"{s['id']}.subscription", nome))
        elif tipos.get("free"):
            alvos.append((s["id"], f"{s['id']}.free", nome))
    con.commit()
    return alvos


# ---------------------------------------------------------------------- conversão
def _poster(show):
    vertical = (show.get("imageSet") or {}).get("verticalPoster") or {}
    return vertical.get("w360") or vertical.get("w480") or vertical.get("w240")


def _tmdb(show):
    """'movie/603' -> ('movie', 603)."""
    valor = show.get("tmdbId") or ""
    if "/" in valor:
        tipo, numero = valor.split("/", 1)
        if numero.isdigit():
            return ("movie" if tipo == "movie" else "tv"), int(numero)
    return None, None


def opcoes_no_brasil(show, mapa_servicos):
    """Agrupa as opções de streaming por plataforma: dublado, legendado, qualidade, link e validade."""
    resultado = {}
    ordem_qualidade = {"sd": 0, "hd": 1, "qhd": 2, "uhd": 3}
    for op in (show.get("streamingOptions") or {}).get(PAIS, []):
        if op.get("type") not in ("subscription", "free", "addon"):
            continue                                   # aluguel e compra não entram
        servico = (op.get("service") or {}).get("id")
        nome = mapa_servicos.get(servico)
        if not nome:
            continue
        info = resultado.setdefault(nome, {"dublado": False, "legendado": False, "qualidade": None,
                                           "link": None, "expira_em": None})
        if any(a.get("language") == IDIOMA_PT for a in op.get("audios") or []):
            info["dublado"] = True
        if any((s.get("locale") or {}).get("language") == IDIOMA_PT for s in op.get("subtitles") or []):
            info["legendado"] = True
        q = op.get("quality")
        if q and ordem_qualidade.get(q, -1) > ordem_qualidade.get(info["qualidade"], -1):
            info["qualidade"] = q
        if op.get("type") != "addon" or not info["link"]:
            info["link"] = op.get("link") or info["link"]
        if op.get("expiresOn"):
            info["expira_em"] = datetime.fromtimestamp(op["expiresOn"], tz=timezone.utc).date().isoformat()
    return resultado


def converter(show, mapa_servicos):
    """Transforma um 'show' da API num registro do catálogo do StreamSmart."""
    tipo_tmdb, tmdb_id = _tmdb(show)
    tipo = "filme" if show.get("showType") == "movie" else "serie"
    generos = normalizar_generos([GENEROS.get(g.get("id"), "") for g in show.get("genres") or []])
    return {
        "tipo": tipo,
        "titulo": show.get("title") or show.get("originalTitle") or "Sem título",
        "ano": show.get("releaseYear") or show.get("firstAirYear"),
        "duracao_min": show.get("runtime") or (100 if tipo == "filme" else 45),
        "generos": generos,
        "sinopse": (show.get("overview") or "").strip() or "Sinopse ainda não disponível.",
        "poster_url": _poster(show),
        "nota": round((show.get("rating") or 0) / 10, 1) or None,
        "tmdb_tipo": tipo_tmdb, "tmdb_id": tmdb_id,
        "plataformas": opcoes_no_brasil(show, mapa_servicos),
    }


# ---------------------------------------------------------------------- gravação
def gravar(con, r, enriquecimento=None):
    """Insere ou atualiza o título e a disponibilidade dele em cada plataforma.

    enriquecimento: registro convertido do TMDB em português (título, sinopse, classificação...), opcional.
    """
    e = enriquecimento or {}
    titulo = e.get("titulo") or r["titulo"]
    dados = {
        "titulo": titulo, "tipo": r["tipo"], "ano": r["ano"] or e.get("ano"),
        "duracao_min": e.get("duracao_min") or r["duracao_min"],
        "generos": ",".join(e.get("generos") or r["generos"]),
        "classificacao": e.get("classificacao"),
        "sinopse": e.get("sinopse") if e.get("sinopse") and not e["sinopse"].startswith("Sinopse ainda") else r["sinopse"],
        "poster_url": r["poster_url"] or e.get("poster_url"),
        "nota_tmdb": r["nota"] or e.get("nota_tmdb"),
        "idioma_original": e.get("idioma_original"),
        "tmdb_id": r["tmdb_id"],
    }
    if not dados["generos"]:
        dados["generos"] = "drama"
    existente = None
    if r["tmdb_id"]:
        existente = con.execute("SELECT id FROM titulos WHERE tmdb_id = ? AND tipo = ?", (r["tmdb_id"], r["tipo"])).fetchone()
    if not existente:
        existente = con.execute("SELECT id FROM titulos WHERE tmdb_id IS NULL AND tipo = ? AND lower(titulo) IN (lower(?), lower(?)) AND ano = ?",
                                (r["tipo"], titulo, r["titulo"], dados["ano"])).fetchone()
    if existente:
        tid = existente["id"]
        con.execute("""UPDATE titulos SET titulo=?, tipo=?, ano=?, duracao_min=?, generos=?,
                       classificacao=COALESCE(?, classificacao), sinopse=?, poster_url=COALESCE(?, poster_url),
                       nota_tmdb=COALESCE(?, nota_tmdb), idioma_original=COALESCE(?, idioma_original),
                       tmdb_id=COALESCE(?, tmdb_id) WHERE id=?""",
                    (dados["titulo"], dados["tipo"], dados["ano"], dados["duracao_min"], dados["generos"],
                     dados["classificacao"], dados["sinopse"], dados["poster_url"], dados["nota_tmdb"],
                     dados["idioma_original"], dados["tmdb_id"], tid))
        novo = False
    else:
        tid = con.execute("""INSERT INTO titulos (titulo, tipo, ano, duracao_min, generos, vibes, classificacao, sinopse,
                             poster_url, nota_tmdb, idioma_original, tmdb_id, origem)
                             VALUES (?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, 'streaming')""",
                          (dados["titulo"], dados["tipo"], dados["ano"], dados["duracao_min"], dados["generos"],
                           dados["classificacao"], dados["sinopse"], dados["poster_url"], dados["nota_tmdb"],
                           dados["idioma_original"], dados["tmdb_id"])).lastrowid
        novo = True
    ids = {row["nome"]: row["id"] for row in con.execute("SELECT id, nome FROM plataformas")}
    for nome, info in r["plataformas"].items():
        con.execute("""INSERT INTO titulo_plataforma (titulo_id, plataforma_id, fonte, dublado, legendado, qualidade, link, expira_em)
                       VALUES (?, ?, 'streaming', ?, ?, ?, ?, ?)
                       ON CONFLICT(titulo_id, plataforma_id) DO UPDATE SET fonte='streaming', dublado=excluded.dublado,
                       legendado=excluded.legendado, qualidade=excluded.qualidade, link=excluded.link, expira_em=excluded.expira_em""",
                    (tid, ids[nome], int(info["dublado"]), int(info["legendado"]), info["qualidade"], info["link"], info["expira_em"]))
    return tid, novo


# ---------------------------------------------------------------------- importação com cota diária
def _ler_json(con, chave, padrao):
    r = con.execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave,)).fetchone()
    try:
        return json.loads(r["valor"]) if r and r["valor"] else padrao
    except ValueError:
        return padrao


def _salvar(con, chave, valor):
    con.execute("INSERT INTO configuracoes (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                (chave, valor if isinstance(valor, str) else json.dumps(valor)))
    con.commit()


def uso_hoje(con):
    uso = _ler_json(con, "streaming_uso", {})
    return uso.get("contagem", 0) if uso.get("dia") == date.today().isoformat() else 0


def importar(con, cliente, limite_diario=95, cliente_tmdb=None, progresso=None):
    """Importa páginas dos catálogos até gastar a cota do dia, em rodízio entre os streamings.

    Rodízio: primeiro a página 1 de todos os streamings (filmes e séries), depois a página 2 de
    todos, e assim por diante. Assim, mesmo com poucas consultas, todos os streamings aparecem.
    Os cursores ficam salvos e a importação continua de onde parou no dia seguinte.
    """
    hoje = date.today().isoformat()
    usadas = uso_hoje(con)
    disponiveis = max(limite_diario - usadas, 0)
    if disponiveis == 0:
        return {"consultas": 0, "novos": 0, "atualizados": 0, "completo": False, "cota_esgotada": True}

    inicio_requisicoes = cliente.requisicoes
    servicos = cliente.servicos()
    alvos = sincronizar_plataformas(con, servicos)
    mapa = carregar_mapa_plataformas()
    for s in servicos:  # serviços novos (fora do JSON) também entram no mapa
        mapa.setdefault(s["id"], mapa.get(_normalizar(s.get("name"))) or s.get("name") or s["id"])

    cursores = _ler_json(con, "streaming_cursores", {})
    filas = [f"{catalogo}|{tipo}" for _, catalogo, _ in alvos for tipo in ("movie", "series")]
    novos = atualizados = 0
    cota_esgotada = False

    def gastas():
        return cliente.requisicoes - inicio_requisicoes

    while gastas() < disponiveis:
        pendentes = [f for f in filas if cursores.get(f) != "fim"]
        if not pendentes:
            break
        for fila in pendentes:
            if gastas() >= disponiveis:
                break
            catalogo, tipo = fila.split("|")
            try:
                pagina = cliente.catalogo(catalogo, tipo, None if cursores.get(fila) in (None, "inicio") else cursores[fila])
            except CotaEsgotada:
                cota_esgotada = True
                break
            for show in pagina.get("shows", []):
                r = converter(show, mapa)
                if not r["plataformas"]:
                    continue
                enriquecimento = None
                if cliente_tmdb and r["tmdb_id"]:
                    try:
                        from .tmdb import converter as converter_tmdb
                        det = cliente_tmdb.detalhes(r["tmdb_tipo"], r["tmdb_id"])
                        if det:
                            enriquecimento = converter_tmdb(r["tmdb_tipo"], det, set())
                    except Exception:   # o complemento em português é opcional
                        enriquecimento = None
                _, foi_novo = gravar(con, r, enriquecimento)
                novos += foi_novo
                atualizados += not foi_novo
            con.commit()
            cursores[fila] = pagina.get("nextCursor") if pagina.get("hasMore") else "fim"
            _salvar(con, "streaming_cursores", cursores)
            _salvar(con, "streaming_uso", {"dia": hoje, "contagem": usadas + gastas()})
            if progresso:
                feitas = sum(1 for f in filas if cursores.get(f) == "fim")
                progresso(f"{catalogo.split('.')[0]}: {novos} novos, {atualizados} atualizados", feitas, len(filas))
        if cota_esgotada:
            break

    completo = all(cursores.get(f) == "fim" for f in filas)
    if completo:
        _salvar(con, "streaming_ciclo_completo", datetime.now().isoformat(timespec="seconds"))
    return {"consultas": gastas(), "novos": novos, "atualizados": atualizados, "completo": completo,
            "cota_esgotada": cota_esgotada or (usadas + gastas() >= limite_diario)}


def reiniciar_ciclo(con):
    """Recomeça a leitura dos catálogos do início (para atualizar disponibilidade, áudios e legendas)."""
    _salvar(con, "streaming_cursores", {})
