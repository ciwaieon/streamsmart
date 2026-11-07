"""Testes da integração com a Streaming Availability API, usando respostas simuladas (sem internet)."""
import io
import re
import urllib.error
import urllib.parse

import pytest

import database
import repositorio as repo
from services import streaming
from services.streaming import ClienteStreaming, converter, importar


def opcao(servico, tipo="subscription", audios=("por", "eng"), legendas=("por",), qualidade="hd", link=None, expira=None):
    return {"service": {"id": servico, "name": servico.title()}, "type": tipo, "quality": qualidade,
            "link": link or f"https://{servico}.exemplo/titulo",
            "audios": [{"language": a} for a in audios],
            "subtitles": [{"closedCaptions": False, "locale": {"language": l}} for l in legendas],
            **({"expiresOn": expira} if expira else {})}


COCO = {"showType": "movie", "title": "Coco", "releaseYear": 2017, "runtime": 105, "tmdbId": "movie/354912",
        "genres": [{"id": "animation"}, {"id": "family"}], "overview": "Miguel dreams of becoming a musician.", "rating": 82,
        "imageSet": {"verticalPoster": {"w360": "https://img.exemplo/coco.jpg"}},
        "streamingOptions": {"br": [opcao("netflix", expira=1798761600), opcao("netflix", tipo="rent", audios=())],
                             "us": [opcao("disney")]}}
CLUBE = {"showType": "movie", "title": "Fight Club", "releaseYear": 1999, "runtime": 139, "tmdbId": "movie/550",
         "genres": [{"id": "drama"}, {"id": "thriller"}], "overview": "An insomniac office worker...", "rating": 84,
         "imageSet": {"verticalPoster": {"w360": "https://img.exemplo/clube.jpg"}},
         "streamingOptions": {"br": [opcao("netflix", audios=("eng",)), opcao("prime", qualidade="uhd"),
                                     opcao("cinestar", audios=("eng",))]}}
DORAMA = {"showType": "series", "title": "Crash Landing on You", "firstAirYear": 2019, "tmdbId": "tv/94796",
          "genres": [{"id": "romance"}, {"id": "comedy"}], "overview": "A paragliding mishap...", "rating": 88,
          "imageSet": {"verticalPoster": {"w360": "https://img.exemplo/cloy.jpg"}},
          "streamingOptions": {"br": [opcao("netflix", audios=("kor",))]}}

SERVICOS = {"countryCode": "br", "services": [
    {"id": "netflix", "name": "Netflix", "themeColorCode": "#E50914", "streamingOptionTypes": {"subscription": True}},
    {"id": "prime", "name": "Prime Video", "themeColorCode": "#00A8E1", "streamingOptionTypes": {"subscription": True, "addon": True}},
    {"id": "cinestar", "name": "Cine Star", "themeColorCode": "#FF0000", "streamingOptionTypes": {"subscription": True}},
    {"id": "loja", "name": "Loja", "themeColorCode": "#000000", "streamingOptionTypes": {"rent": True, "buy": True}},
]}


def falsa_api(chamadas, recusar_primeiro_host=False, cota_apos=None):
    """Simula a API: a Netflix tem 2 páginas de filmes e 1 de séries; o Prime e a Cine Star, 1 cada."""
    def buscar(url, cabecalhos):
        partes = urllib.parse.urlparse(url)
        params = dict(urllib.parse.parse_qsl(partes.query))
        chamadas.append((partes.netloc, partes.path, params, cabecalhos))
        if recusar_primeiro_host and "X-API-Key" in cabecalhos:
            raise urllib.error.HTTPError(url, 403, "Forbidden", None, io.BytesIO())
        if cota_apos is not None and len(chamadas) > cota_apos:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", None, io.BytesIO())
        if partes.path.endswith("/countries/br"):
            return SERVICOS
        catalogo, tipo, cursor = params["catalogs"], params["show_type"], params.get("cursor")
        if catalogo == "netflix.subscription" and tipo == "movie":
            return {"shows": [COCO], "hasMore": True, "nextCursor": "p2"} if not cursor else {"shows": [CLUBE], "hasMore": False}
        if catalogo == "netflix.subscription" and tipo == "series":
            return {"shows": [DORAMA], "hasMore": False}
        if catalogo == "prime.subscription" and tipo == "movie":
            return {"shows": [CLUBE], "hasMore": False}
        if catalogo == "cinestar.subscription" and tipo == "movie":
            return {"shows": [CLUBE], "hasMore": False}
        return {"shows": [], "hasMore": False}
    return buscar


@pytest.fixture
def con(tmp_path):
    caminho = str(tmp_path / "s.db")
    database.inicializar(caminho, com_demo=True)
    c = database.conectar(caminho)
    yield c
    c.close()


def test_converter_le_dublado_legendado_e_ignora_aluguel():
    mapa = streaming.carregar_mapa_plataformas()
    r = converter(COCO, mapa)
    assert r["tipo"] == "filme" and r["ano"] == 2017 and r["tmdb_id"] == 354912 and r["nota"] == 8.2
    assert r["generos"] == ["animação", "família"] and r["poster_url"].endswith("coco.jpg")
    assert list(r["plataformas"]) == ["Netflix"]                       # só o Brasil e só assinatura
    assert r["plataformas"]["Netflix"]["dublado"] and r["plataformas"]["Netflix"]["legendado"]
    assert r["plataformas"]["Netflix"]["expira_em"] == "2027-01-01"
    clube = converter(CLUBE, mapa)["plataformas"]
    assert clube["Netflix"]["dublado"] is False and clube["Netflix"]["legendado"] is True
    assert clube["Prime Video"]["qualidade"] == "uhd"


def test_importa_em_rodizio_respeitando_a_cota_e_continua_depois(con):
    chamadas = []
    cliente = ClienteStreaming("chave", buscar=falsa_api(chamadas))
    # cota de 4 consultas: 1 para a lista de serviços + 3 páginas (uma de cada fila, em rodízio)
    r = importar(con, cliente, limite_diario=4)
    assert r["consultas"] == 4 and r["cota_esgotada"] and not r["completo"]
    assert streaming.uso_hoje(con) == 4
    # streaming novo entrou sozinho, com a cor suavizada; a loja (só aluguel/compra) não
    cine = con.execute("SELECT cor FROM plataformas WHERE nome = 'Cine Star'").fetchone()
    assert cine and cine["cor"] != "#FF0000"
    assert con.execute("SELECT 1 FROM plataformas WHERE nome = 'Loja'").fetchone() is None
    # no mesmo dia, sem cota, não faz nada
    assert importar(con, cliente, limite_diario=4)["consultas"] == 0
    # com cota maior, continua de onde parou e termina o ciclo
    r = importar(con, cliente, limite_diario=50)
    assert r["completo"]
    netflix_filmes = [c for c in chamadas if c[2].get("catalogs") == "netflix.subscription" and c[2].get("show_type") == "movie"]
    assert [c[2].get("cursor") for c in netflix_filmes] == [None, "p2"]   # retomou pelo cursor salvo


def test_grava_disponibilidade_e_aproveita_titulo_existente(con):
    coco_demo = con.execute("SELECT id FROM titulos WHERE titulo = 'Coco'").fetchone()["id"]
    importar(con, ClienteStreaming("chave", buscar=falsa_api([])), limite_diario=50)
    coco = con.execute("SELECT * FROM titulos WHERE tmdb_id = 354912").fetchall()
    assert len(coco) == 1 and coco[0]["id"] == coco_demo and coco[0]["poster_url"].endswith("coco.jpg")
    plats = {p["nome"]: p for p in repo.plataformas_do_titulo(con, coco_demo)}
    assert plats["Netflix"]["fonte"] == "streaming" and plats["Netflix"]["dublado"] == 1
    assert plats["Netflix"]["link"] == "https://netflix.exemplo/titulo"
    clube_id = con.execute("SELECT id FROM titulos WHERE tmdb_id = 550").fetchone()["id"]
    plats = {p["nome"]: p for p in repo.plataformas_do_titulo(con, clube_id)}
    assert plats["Netflix"]["dublado"] == 0 and plats["Netflix"]["legendado"] == 1 and plats["Prime Video"]["dublado"] == 1
    catalogo = {t["id"]: t for t in repo.listar_catalogo(con)}
    assert catalogo[clube_id]["tem_dublado"] is True and catalogo[clube_id]["tem_legenda"] is True


def test_cota_esgotada_pela_api_para_sem_erro(con):
    r = importar(con, ClienteStreaming("chave", buscar=falsa_api([], cota_apos=2)), limite_diario=50)
    assert r["cota_esgotada"] and r["consultas"] >= 2


def test_chave_da_rapidapi_funciona_trocando_de_servidor():
    chamadas = []
    cliente = ClienteStreaming("chave-rapid", buscar=falsa_api(chamadas, recusar_primeiro_host=True))
    assert cliente.servicos()[0]["id"] == "netflix"
    assert chamadas[0][0] == "api.movieofthenight.com"
    assert chamadas[-1][0] == "streaming-availability.p.rapidapi.com"
    assert chamadas[-1][3]["X-RapidAPI-Key"] == "chave-rapid"


def test_tela_do_titulo_mostra_dublado_legendado_e_link(tmp_path):
    import app as aplicacao
    caminho = str(tmp_path / "tela.db")
    database.inicializar(caminho, com_demo=True)
    con = database.conectar(caminho)
    importar(con, ClienteStreaming("chave", buscar=falsa_api([])), limite_diario=50)
    clube_id = con.execute("SELECT id FROM titulos WHERE tmdb_id = 550").fetchone()["id"]
    con.close()
    aplicacao.app.config.update(TESTING=True, DATABASE=caminho)
    with aplicacao.app.test_client() as c:
        c.post("/login", data={"email": "demo@streamsmart.com", "senha": "demo123"})
        html = c.get(f"/titulo/{clube_id}").get_data(as_text=True)
        assert "Sem dublagem" in html and "Legendado" in html and "4K" in html
        assert 'href="https://netflix.exemplo/titulo"' in html and "Abrir na Netflix" in html
        # filtro "tem dublagem": Fight Club entra (o Prime tem áudio em português); o dorama não
        html = c.get("/recomendar?tempo=livre&companhia=sozinho&classificacao=18&audio=dublado").get_data(as_text=True)
        assert "Fight Club" in html and "Crash Landing on You" not in html
        assert "Streaming Availability API" in html                     # atribuição obrigatória
