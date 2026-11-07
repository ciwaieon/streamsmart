"""Testes da integração com o TMDB usando respostas simuladas (sem acessar a internet)."""
import urllib.parse

import pytest

import database
import repositorio as repo
from services.tmdb import ClienteTMDB, ErroTMDB, converter, importar

PROVEDORES = {"results": [
    {"provider_id": 8, "provider_name": "Netflix"},
    {"provider_id": 119, "provider_name": "Amazon Prime Video"},
    {"provider_id": 999, "provider_name": "Serviço Desconhecido"},
]}
FILME = {"id": 550, "title": "Clube da Luta", "release_date": "1999-10-15", "runtime": 139,
         "genres": [{"id": 18}, {"id": 53}], "overview": "Um homem insone conhece um vendedor de sabão.",
         "poster_path": "/abc.jpg", "vote_average": 8.43,
         "release_dates": {"results": [{"iso_3166_1": "US", "release_dates": [{"certification": "R"}]},
                                       {"iso_3166_1": "BR", "release_dates": [{"certification": ""}, {"certification": "18"}]}]}}
SERIE = {"id": 1399, "name": "A Guerra dos Tronos", "first_air_date": "2011-04-17", "episode_run_time": [],
         "last_episode_to_air": {"runtime": 58}, "genres": [{"id": 10765}, {"id": 18}], "overview": "",
         "poster_path": None, "vote_average": 8.4,
         "content_ratings": {"results": [{"iso_3166_1": "BR", "rating": "16"}]}}
COCO = {"id": 354912, "title": "Coco", "release_date": "2017-10-27", "runtime": 105, "genres": [{"id": 16}, {"id": 10751}],
        "overview": "Miguel sonha em ser músico.", "poster_path": "/coco.jpg", "vote_average": 8.2,
        "release_dates": {"results": [{"iso_3166_1": "BR", "release_dates": [{"certification": "L"}]}]}}


def falso_tmdb(chamadas):
    """Simula a API: devolve respostas conforme o caminho pedido."""
    def buscar(url, cabecalhos):
        caminho = urllib.parse.urlparse(url).path.replace("/3", "", 1)
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        chamadas.append((caminho, params, cabecalhos))
        if caminho.startswith("/watch/providers"):
            return PROVEDORES
        if caminho == "/discover/movie":
            ids = {"8": [{"id": 550}, {"id": 354912}], "119": [{"id": 550}]}[params["with_watch_providers"]]
            return {"results": ids, "total_pages": 1}
        if caminho == "/discover/tv":
            return {"results": [{"id": 1399}] if params["with_watch_providers"] == "119" else [], "total_pages": 1}
        return {"/movie/550": FILME, "/tv/1399": SERIE, "/movie/354912": COCO, "/configuration": {}}[caminho]
    return buscar


def test_converter_filme_e_serie():
    f = converter("movie", FILME, {"Netflix"})
    assert f["tipo"] == "filme" and f["ano"] == 1999 and f["duracao_min"] == 139
    assert f["generos"] == ["drama", "suspense"] and f["classificacao"] == "18" and f["nota_tmdb"] == 8.4
    assert f["poster_url"].endswith("/abc.jpg")
    s = converter("tv", SERIE, {"Prime Video"})
    assert s["tipo"] == "serie" and s["duracao_min"] == 58 and s["classificacao"] == "16"
    assert s["generos"] == ["ficção científica", "fantasia", "drama"]
    assert "Sinopse" in s["sinopse"] and s["poster_url"] is None


def test_autenticacao_v3_e_v4():
    chamadas = []
    ClienteTMDB("abc123", buscar=falso_tmdb(chamadas)).testar()
    assert chamadas[-1][1]["api_key"] == "abc123"
    ClienteTMDB("eyJtoken", buscar=falso_tmdb(chamadas)).testar()
    assert chamadas[-1][2]["Authorization"] == "Bearer eyJtoken" and "api_key" not in chamadas[-1][1]
    with pytest.raises(ErroTMDB):
        ClienteTMDB("  ")


def test_importar_grava_titulos_plataformas_e_aproveita_os_existentes(tmp_path):
    caminho = str(tmp_path / "t.db")
    database.inicializar(caminho, com_demo=True)
    con = database.conectar(caminho)
    coco_antes = con.execute("SELECT id FROM titulos WHERE titulo = 'Coco'").fetchone()["id"]
    chamadas = []
    r = importar(con, ClienteTMDB("x", buscar=falso_tmdb(chamadas)), paginas=1, trabalhadores=2)
    assert r == {"novos": 2, "atualizados": 1, "total": 71}
    # Coco já existia no catálogo de demonstração: foi atualizado, sem duplicar (histórico preservado)
    coco = con.execute("SELECT * FROM titulos WHERE titulo = 'Coco'").fetchall()
    assert len(coco) == 1 and coco[0]["id"] == coco_antes and coco[0]["tmdb_id"] == 354912
    clube = repo.buscar_titulo(con, con.execute("SELECT id FROM titulos WHERE tmdb_id = 550").fetchone()["id"])
    plataformas = {p["nome"] for p in repo.plataformas_do_titulo(con, clube["id"])}
    assert plataformas == {"Netflix", "Prime Video"}        # apareceu nas duas plataformas
    # só assinatura (flatrate) e região Brasil
    descobertas = [c for c in chamadas if c[0].startswith("/discover")]
    assert all(c[1]["watch_region"] == "BR" and c[1]["with_watch_monetization_types"] == "flatrate" for c in descobertas)
    # importar de novo não duplica
    r2 = importar(con, ClienteTMDB("x", buscar=falso_tmdb([])), paginas=1, trabalhadores=2)
    assert r2["novos"] == 0 and r2["total"] == 71


def test_migracao_de_banco_antigo(tmp_path):
    """Um banco da versão 1 (sem colunas do TMDB nem tabelas novas) é atualizado sozinho."""
    import sqlite3
    caminho = str(tmp_path / "antigo.db")
    con = sqlite3.connect(caminho)
    con.executescript("""
        CREATE TABLE titulos (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, tipo TEXT NOT NULL, ano INTEGER,
            duracao_min INTEGER NOT NULL, generos TEXT NOT NULL, vibes TEXT NOT NULL, classificacao TEXT NOT NULL, sinopse TEXT NOT NULL);
        INSERT INTO titulos (titulo, tipo, ano, duracao_min, generos, vibes, classificacao, sinopse)
            VALUES ('Antigo', 'filme', 2000, 90, 'policial,comédia', 'rir', '12', 'x');""")
    con.close()
    database.inicializar(caminho, com_demo=False)
    con = database.conectar(caminho)
    colunas = {r["name"] for r in con.execute("PRAGMA table_info(titulos)")}
    assert {"tmdb_id", "poster_url", "nota_tmdb", "origem"} <= colunas
    assert con.execute("SELECT generos FROM titulos WHERE titulo = 'Antigo'").fetchone()[0] == "crime,comédia"
    assert con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name IN ('avaliacoes', 'amizades', 'configuracoes')").fetchone()[0] == 3
