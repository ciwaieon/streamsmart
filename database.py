"""
Camada de acesso ao banco de dados (SQLite).

Responsável por abrir conexões, criar e atualizar as tabelas (migração automática
para bancos criados por versões anteriores) e popular o banco com o catálogo de
demonstração e os usuários de exemplo.
"""
import json
import os
import sqlite3
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from services.categorias import normalizar_generos

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")
CATALOGO_PATH = os.path.join(BASE_DIR, "data", "catalogo.json")
PLATAFORMAS_PATH = os.path.join(BASE_DIR, "data", "plataformas.json")
DB_PADRAO = os.path.join(BASE_DIR, "streamsmart.db")


def conectar(caminho=None):
    """Abre uma conexão com o banco; as linhas são acessíveis por nome de coluna."""
    con = sqlite3.connect(caminho or os.environ.get("STREAMSMART_DB", DB_PADRAO), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")   # permite ler o banco enquanto a importação grava
    return con


def _colunas(con, tabela):
    return {r["name"] for r in con.execute(f"PRAGMA table_info({tabela})")}


def criar_tabelas(con):
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        con.executescript(f.read())
    # Migração: bancos da versão 1 não têm as colunas do TMDB
    novas = {
        "titulos": [("tmdb_id", "INTEGER"), ("poster_url", "TEXT"), ("nota_tmdb", "REAL"),
                    ("origem", "TEXT NOT NULL DEFAULT 'demo'"), ("idioma_original", "TEXT")],
        "usuarios": [("usuario", "TEXT")],
        "historico": [("audio", "TEXT")],
        "titulo_plataforma": [("fonte", "TEXT"), ("dublado", "INTEGER"), ("legendado", "INTEGER"),
                              ("qualidade", "TEXT"), ("link", "TEXT"), ("expira_em", "TEXT")],
    }
    for tabela, colunas in novas.items():
        existentes = _colunas(con, tabela)
        for coluna, tipo in colunas:
            if coluna not in existentes:
                con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    # usuários antigos ganham um nome de usuário a partir do e-mail
    for r in con.execute("SELECT id, email FROM usuarios WHERE usuario IS NULL").fetchall():
        con.execute("UPDATE usuarios SET usuario = ? WHERE id = ?", (gerar_usuario(con, r["email"].split("@")[0]), r["id"]))
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_usuario ON usuarios(usuario)")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_titulos_tmdb ON titulos(tipo, tmdb_id) WHERE tmdb_id IS NOT NULL")
    con.commit()


def gerar_usuario(con, base):
    """Cria um nome de usuário válido e ainda não usado a partir de um texto (ex.: parte do e-mail)."""
    import re
    base = re.sub(r"[^a-z0-9_.]", "", base.lower())[:18] or "usuario"
    if len(base) < 3:
        base = (base + "usr")[:3]
    candidato, n = base, 1
    while con.execute("SELECT 1 FROM usuarios WHERE usuario = ?", (candidato,)).fetchone():
        n += 1
        candidato = f"{base[:16]}{n}"
    return candidato


def ler_plataformas():
    with open(PLATAFORMAS_PATH, encoding="utf-8") as f:
        return json.load(f)["plataformas"]


def carregar_catalogo(con):
    """Insere/atualiza plataformas e o catálogo de demonstração a partir dos arquivos JSON."""
    with open(CATALOGO_PATH, encoding="utf-8") as f:
        dados = json.load(f)

    for p in ler_plataformas():
        con.execute("INSERT INTO plataformas (nome, cor) VALUES (?, ?) ON CONFLICT(nome) DO UPDATE SET cor = excluded.cor",
                    (p["nome"], p["cor"]))
    ids_plataforma = {r["nome"]: r["id"] for r in con.execute("SELECT id, nome FROM plataformas")}

    if con.execute("SELECT COUNT(*) FROM titulos WHERE origem = 'demo'").fetchone()[0] == 0:
        for t in dados["titulos"]:
            cur = con.execute(
                """INSERT INTO titulos (titulo, tipo, ano, duracao_min, generos, vibes, classificacao, sinopse, origem, idioma_original)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'demo', ?)""",
                (t["titulo"], t["tipo"], t["ano"], t["duracao_min"], ",".join(normalizar_generos(t["generos"].split(","))),
                 t["vibes"], t["classificacao"], t["sinopse"], t.get("idioma", "en")))
            for nome in t["plataformas"]:
                con.execute("INSERT INTO titulo_plataforma (titulo_id, plataforma_id, fonte) VALUES (?, ?, 'demo')",
                            (cur.lastrowid, ids_plataforma[nome]))
    else:
        # bancos antigos: padroniza os gêneros já gravados
        for r in con.execute("SELECT id, generos FROM titulos WHERE origem = 'demo'").fetchall():
            con.execute("UPDATE titulos SET generos = ? WHERE id = ?",
                        (",".join(normalizar_generos(r["generos"].split(","))), r["id"]))
    con.commit()


def _criar_usuario(con, nome, email, senha, usuario):
    cur = con.execute("INSERT INTO usuarios (nome, usuario, email, senha_hash) VALUES (?, ?, ?, ?)",
                      (nome, usuario, email, generate_password_hash(senha)))
    return cur.lastrowid


def _titulo(con, nome):
    return con.execute("SELECT id, duracao_min FROM titulos WHERE titulo = ? AND origem = 'demo' OR (titulo = ? AND tmdb_id IS NOT NULL) LIMIT 1",
                       (nome, nome)).fetchone()


def criar_usuario_demo(con, hoje=None):
    """Cria o usuário demo@streamsmart.com (senha: demo123) com assinaturas e histórico.

    Os dados são montados em relação à data de hoje, para que os alertas e o
    relatório sempre mostrem situações interessantes na apresentação.
    """
    if con.execute("SELECT 1 FROM usuarios WHERE email = 'demo@streamsmart.com'").fetchone():
        return
    hoje = hoje or date.today()
    uid = _criar_usuario(con, "Usuário Demo", "demo@streamsmart.com", "demo123", "demo")
    plat = {r["nome"]: r["id"] for r in con.execute("SELECT id, nome FROM plataformas")}

    def dia_daqui(n):
        return (hoje + timedelta(days=n)).day

    mes_prime = (hoje + timedelta(days=4)).month
    assinaturas = [
        # plataforma, plano, valor, periodicidade, dia, mês (anual), fim do teste
        ("Netflix", "Padrão", 44.90, "mensal", dia_daqui(2), None, None),
        ("HBO Max", "Básico com anúncios", 29.90, "mensal", dia_daqui(12), None, None),
        ("Disney+", "Padrão", 46.90, "mensal", dia_daqui(20), None, None),
        ("Prime Video", "Anual", 166.80, "anual", dia_daqui(4), mes_prime, None),
        ("Paramount+", "Teste grátis", 0.00, "mensal", dia_daqui(3), None, (hoje + timedelta(days=3)).isoformat()),
    ]
    for nome, plano, valor, per, dia, mes, teste in assinaturas:
        con.execute(
            """INSERT INTO assinaturas (usuario_id, plataforma_id, plano, valor, periodicidade,
                                        dia_vencimento, mes_vencimento, fim_teste)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, plat[nome], plano, valor, per, dia, mes, teste),
        )

    # Histórico: muito uso de Netflix, pouco de Disney+, nada de HBO Max há mais de 60 dias.
    historico = [
        ("Stranger Things", "Netflix", 1, 2), ("Stranger Things", "Netflix", 2, 3),
        ("Brooklyn Nine-Nine", "Netflix", 3, 4), ("Brooklyn Nine-Nine", "Netflix", 5, 3),
        ("Glass Onion", "Netflix", 7, 1), ("Dark", "Netflix", 9, 2), ("Round 6", "Netflix", 12, 3),
        ("Wandinha", "Netflix", 15, 2), ("Heartstopper", "Netflix", 18, 3),
        ("Coco", "Disney+", 10, 1),
        ("Reacher", "Prime Video", 6, 2), ("Interestelar", "Prime Video", 20, 1),
        ("The Office", "Prime Video", 22, 4),
        ("Succession", "HBO Max", 70, 2), ("Parasita", "HBO Max", 85, 1),
    ]
    legendados = {"Dark", "Round 6", "Succession", "Parasita", "Stranger Things"}
    for titulo, nome_plat, dias_atras, qtd in historico:
        t = _titulo(con, titulo)
        con.execute(
            "INSERT INTO historico (usuario_id, titulo_id, plataforma_id, data, minutos, audio) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, t["id"], plat[nome_plat], (hoje - timedelta(days=dias_atras)).isoformat(), t["duracao_min"] * qtd,
             "legendado" if titulo in legendados else "dublado"),
        )
    for titulo, nota, comentario in [
        ("Stranger Things", 5, "Maratonei em dois dias."),
        ("Dark", 4, "Confuso no começo, genial no fim."),
        ("Coco", 5, "Chorei no final, como todo mundo."),
        ("Glass Onion", 3, None),
    ]:
        con.execute("INSERT INTO avaliacoes (usuario_id, titulo_id, nota, comentario) VALUES (?, ?, ?, ?)",
                    (uid, _titulo(con, titulo)["id"], nota, comentario))
    con.commit()


def criar_amigos_demo(con):
    """Cria três usuários de exemplo, amizades com o usuário demo e avaliações deles."""
    demo = con.execute("SELECT id FROM usuarios WHERE email = 'demo@streamsmart.com'").fetchone()
    if demo is None or con.execute("SELECT 1 FROM usuarios WHERE email = 'ana@streamsmart.com'").fetchone():
        return
    ana = _criar_usuario(con, "Ana Souza", "ana@streamsmart.com", "ana12345", "ana.souza")
    bruno = _criar_usuario(con, "Bruno Lima", "bruno@streamsmart.com", "bruno123", "brunolima")
    carla = _criar_usuario(con, "Carla Mendes", "carla@streamsmart.com", "carla123", "carla.m")
    con.executemany("INSERT INTO amizades (solicitante_id, destinatario_id, status) VALUES (?, ?, ?)",
                    [(demo["id"], ana, "aceita"), (bruno, demo["id"], "aceita"), (carla, demo["id"], "pendente")])
    avaliacoes = [
        (ana, "Ted Lasso", 5, "A série mais gentil que já vi."),
        (ana, "Coco", 5, "Trilha sonora maravilhosa."),
        (ana, "Questão de Tempo", 5, "Perfeito para ver em casal."),
        (ana, "Round 6", 2, "Violento demais para mim."),
        (ana, "O Auto da Compadecida", 5, "Clássico absoluto."),
        (ana, "Heartstopper", 4, None),
        (bruno, "Round 6", 5, "Não dá para parar de ver."),
        (bruno, "Stranger Things", 4, "A primeira temporada é a melhor."),
        (bruno, "Duna", 5, "Precisa ver na maior tela possível."),
        (bruno, "Top Gun: Maverick", 4, "Adrenalina pura."),
        (bruno, "The Office", 5, "Revejo todo ano."),
        (bruno, "Corra!", 4, None),
        (carla, "Bluey", 5, "Meus filhos amam, e eu também."),
    ]
    plat = {r["nome"]: r["id"] for r in con.execute("SELECT id, nome FROM plataformas")}
    hoje = date.today()
    for uid, titulo, nota, comentario in avaliacoes:
        t = _titulo(con, titulo)
        if t:
            con.execute("INSERT INTO avaliacoes (usuario_id, titulo_id, nota, comentario) VALUES (?, ?, ?, ?)",
                        (uid, t["id"], nota, comentario))
            # quem avaliou também assistiu: registra no histórico com o áudio escolhido
            p = con.execute("SELECT plataforma_id FROM titulo_plataforma WHERE titulo_id = ? LIMIT 1", (t["id"],)).fetchone()
            if p:
                audio = "legendado" if (uid == bruno and titulo != "The Office") else "dublado"
                con.execute("INSERT INTO historico (usuario_id, titulo_id, plataforma_id, data, minutos, audio) VALUES (?, ?, ?, ?, ?, ?)",
                            (uid, t["id"], p["plataforma_id"], (hoje - timedelta(days=5)).isoformat(), t["duracao_min"], audio))
    con.commit()


def inicializar(caminho=None, com_demo=True):
    con = conectar(caminho)
    criar_tabelas(con)
    carregar_catalogo(con)
    if com_demo:
        criar_usuario_demo(con)
        criar_amigos_demo(con)
    con.close()


if __name__ == "__main__":
    inicializar()
    print("Banco de dados inicializado em", DB_PADRAO)
