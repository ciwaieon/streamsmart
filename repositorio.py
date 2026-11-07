"""
Consultas SQL do sistema (camada de repositório).

Todas as consultas usam parâmetros (?) para evitar injeção de SQL.
"""


# ----------------------------- Usuários -----------------------------
def buscar_usuario_por_email(con, email):
    return con.execute("SELECT * FROM usuarios WHERE email = ?", (email.strip().lower(),)).fetchone()


def buscar_usuario(con, uid):
    return con.execute("SELECT * FROM usuarios WHERE id = ?", (uid,)).fetchone()


def criar_usuario(con, nome, email, senha_hash):
    cur = con.execute("INSERT INTO usuarios (nome, email, senha_hash) VALUES (?, ?, ?)",
                      (nome.strip(), email.strip().lower(), senha_hash))
    con.commit()
    return cur.lastrowid


def atualizar_senha(con, uid, senha_hash):
    con.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (senha_hash, uid))
    con.commit()


def salvar_token(con, uid, token, expira_em):
    con.execute("INSERT INTO tokens_recuperacao (usuario_id, token, expira_em) VALUES (?, ?, ?)",
                (uid, token, expira_em))
    con.commit()


def buscar_token_valido(con, token, agora_iso):
    return con.execute(
        "SELECT * FROM tokens_recuperacao WHERE token = ? AND usado = 0 AND expira_em > ?",
        (token, agora_iso)).fetchone()


def marcar_token_usado(con, token_id):
    con.execute("UPDATE tokens_recuperacao SET usado = 1 WHERE id = ?", (token_id,))
    con.commit()


# ---------------------------- Plataformas ----------------------------
def listar_plataformas(con):
    return [dict(r) for r in con.execute("SELECT * FROM plataformas ORDER BY nome")]


# ---------------------------- Assinaturas ----------------------------
_SELECT_ASSINATURA = """
    SELECT a.*, p.nome AS plataforma, p.cor AS cor
    FROM assinaturas a JOIN plataformas p ON p.id = a.plataforma_id
"""


def listar_assinaturas(con, uid):
    return [dict(r) for r in con.execute(_SELECT_ASSINATURA + " WHERE a.usuario_id = ? ORDER BY p.nome", (uid,))]


def buscar_assinatura(con, uid, aid):
    r = con.execute(_SELECT_ASSINATURA + " WHERE a.usuario_id = ? AND a.id = ?", (uid, aid)).fetchone()
    return dict(r) if r else None


def criar_assinatura(con, uid, d):
    cur = con.execute(
        """INSERT INTO assinaturas (usuario_id, plataforma_id, plano, valor, periodicidade,
                                    dia_vencimento, mes_vencimento, fim_teste)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (uid, d["plataforma_id"], d["plano"], d["valor"], d["periodicidade"],
         d["dia_vencimento"], d["mes_vencimento"], d["fim_teste"]))
    con.commit()
    return cur.lastrowid


def atualizar_assinatura(con, uid, aid, d):
    con.execute(
        """UPDATE assinaturas SET plataforma_id = ?, plano = ?, valor = ?, periodicidade = ?,
                  dia_vencimento = ?, mes_vencimento = ?, fim_teste = ?
           WHERE id = ? AND usuario_id = ?""",
        (d["plataforma_id"], d["plano"], d["valor"], d["periodicidade"], d["dia_vencimento"],
         d["mes_vencimento"], d["fim_teste"], aid, uid))
    con.commit()


def excluir_assinatura(con, uid, aid):
    con.execute("DELETE FROM assinaturas WHERE id = ? AND usuario_id = ?", (aid, uid))
    con.commit()


# ------------------------------ Catálogo ------------------------------
def listar_catalogo(con):
    """Devolve todos os títulos com suas listas de gêneros, vibes e plataformas."""
    plataformas_por_titulo = {}
    for r in con.execute("""SELECT tp.titulo_id, p.id, p.nome, p.cor FROM titulo_plataforma tp
                            JOIN plataformas p ON p.id = tp.plataforma_id ORDER BY p.nome"""):
        plataformas_por_titulo.setdefault(r["titulo_id"], []).append({"id": r["id"], "nome": r["nome"], "cor": r["cor"]})

    catalogo = []
    for r in con.execute("SELECT * FROM titulos ORDER BY titulo"):
        t = dict(r)
        t["generos"] = [g.strip() for g in t["generos"].split(",")]
        t["vibes"] = [v.strip() for v in t["vibes"].split(",")]
        t["plataformas"] = plataformas_por_titulo.get(t["id"], [])
        catalogo.append(t)
    return catalogo


def buscar_titulo(con, tid):
    r = con.execute("SELECT * FROM titulos WHERE id = ?", (tid,)).fetchone()
    return dict(r) if r else None


def plataformas_do_titulo(con, tid):
    return [dict(r) for r in con.execute(
        """SELECT p.* FROM plataformas p JOIN titulo_plataforma tp ON tp.plataforma_id = p.id
           WHERE tp.titulo_id = ? ORDER BY p.nome""", (tid,))]


# ------------------------------ Histórico ------------------------------
def listar_historico(con, uid):
    return [dict(r) for r in con.execute(
        """SELECT h.*, t.titulo, t.tipo, p.nome AS plataforma, p.cor
           FROM historico h
           JOIN titulos t ON t.id = h.titulo_id
           JOIN plataformas p ON p.id = h.plataforma_id
           WHERE h.usuario_id = ? ORDER BY h.data DESC, h.id DESC""", (uid,))]


def registrar_historico(con, uid, titulo_id, plataforma_id, data, minutos):
    con.execute("INSERT INTO historico (usuario_id, titulo_id, plataforma_id, data, minutos) VALUES (?, ?, ?, ?, ?)",
                (uid, titulo_id, plataforma_id, data, minutos))
    con.commit()


def excluir_historico(con, uid, hid):
    con.execute("DELETE FROM historico WHERE id = ? AND usuario_id = ?", (hid, uid))
    con.commit()
