"""
Camada de acesso ao banco de dados (SQLite).

Responsável por abrir conexões, criar as tabelas a partir do schema.sql
e popular o banco com o catálogo e um usuário de demonstração.
"""
import json
import os
import sqlite3
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")
CATALOGO_PATH = os.path.join(BASE_DIR, "data", "catalogo.json")
DB_PADRAO = os.path.join(BASE_DIR, "streamsmart.db")


def conectar(caminho=None):
    """Abre uma conexão com o banco; as linhas são acessíveis por nome de coluna."""
    con = sqlite3.connect(caminho or os.environ.get("STREAMSMART_DB", DB_PADRAO))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def criar_tabelas(con):
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        con.executescript(f.read())


def carregar_catalogo(con):
    """Insere plataformas e títulos do arquivo JSON (apenas se o catálogo estiver vazio)."""
    if con.execute("SELECT COUNT(*) FROM titulos").fetchone()[0] > 0:
        return
    with open(CATALOGO_PATH, encoding="utf-8") as f:
        dados = json.load(f)

    for p in dados["plataformas"]:
        con.execute("INSERT OR IGNORE INTO plataformas (nome, cor) VALUES (?, ?)", (p["nome"], p["cor"]))
    ids_plataforma = {r["nome"]: r["id"] for r in con.execute("SELECT id, nome FROM plataformas")}

    for t in dados["titulos"]:
        cur = con.execute(
            """INSERT INTO titulos (titulo, tipo, ano, duracao_min, generos, vibes, classificacao, sinopse)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (t["titulo"], t["tipo"], t["ano"], t["duracao_min"], t["generos"], t["vibes"],
             t["classificacao"], t["sinopse"]),
        )
        for nome in t["plataformas"]:
            con.execute("INSERT INTO titulo_plataforma (titulo_id, plataforma_id) VALUES (?, ?)",
                        (cur.lastrowid, ids_plataforma[nome]))
    con.commit()


def criar_usuario_demo(con, hoje=None):
    """Cria o usuário demo@streamsmart.com (senha: demo123) com assinaturas e histórico.

    Os dados são montados em relação à data de hoje, para que os alertas e o
    relatório sempre mostrem situações interessantes na apresentação.
    """
    if con.execute("SELECT 1 FROM usuarios WHERE email = 'demo@streamsmart.com'").fetchone():
        return
    hoje = hoje or date.today()
    cur = con.execute("INSERT INTO usuarios (nome, email, senha_hash) VALUES (?, ?, ?)",
                      ("Usuário Demo", "demo@streamsmart.com", generate_password_hash("demo123")))
    uid = cur.lastrowid
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

    def tid(titulo):
        return con.execute("SELECT id, duracao_min FROM titulos WHERE titulo = ?", (titulo,)).fetchone()

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
    for titulo, nome_plat, dias_atras, qtd in historico:
        t = tid(titulo)
        con.execute(
            "INSERT INTO historico (usuario_id, titulo_id, plataforma_id, data, minutos) VALUES (?, ?, ?, ?, ?)",
            (uid, t["id"], plat[nome_plat], (hoje - timedelta(days=dias_atras)).isoformat(), t["duracao_min"] * qtd),
        )
    con.commit()


def inicializar(caminho=None, com_demo=True):
    con = conectar(caminho)
    criar_tabelas(con)
    carregar_catalogo(con)
    if com_demo:
        criar_usuario_demo(con)
    con.close()


if __name__ == "__main__":
    inicializar()
    print("Banco de dados inicializado em", DB_PADRAO)
