"""
Consultas SQL do sistema (camada de repositório).

Todas as consultas usam parâmetros (?) para evitar injeção de SQL.
"""
from services.categorias import VIBES_ANTIGAS


# ----------------------------- Usuários -----------------------------
def buscar_usuario_por_email(con, email):
    return con.execute("SELECT * FROM usuarios WHERE email = ?", (email.strip().lower(),)).fetchone()


def buscar_usuario_por_usuario(con, usuario):
    return con.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario.strip().lstrip("@").lower(),)).fetchone()


def buscar_pessoas(con, uid, termo, limite=10):
    """Procura pessoas pelo nome de usuário ou pelo nome (não mostra o próprio usuário)."""
    termo = termo.strip().lstrip("@").lower()
    if len(termo) < 2:
        return []
    padrao = f"%{termo}%"
    return [dict(r) for r in con.execute(
        """SELECT id, nome, usuario FROM usuarios WHERE id <> ? AND (usuario LIKE ? OR lower(nome) LIKE ?)
           ORDER BY (usuario = ?) DESC, usuario LIMIT ?""", (uid, padrao, padrao, termo, limite))]


def buscar_usuario(con, uid):
    return con.execute("SELECT * FROM usuarios WHERE id = ?", (uid,)).fetchone()


def criar_usuario(con, nome, email, senha_hash, usuario):
    cur = con.execute("INSERT INTO usuarios (nome, usuario, email, senha_hash) VALUES (?, ?, ?, ?)",
                      (nome.strip(), usuario.strip().lstrip("@").lower(), email.strip().lower(), senha_hash))
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
    for r in con.execute("""SELECT tp.titulo_id, p.id, p.nome, p.cor, tp.fonte, tp.dublado, tp.legendado, tp.link
                            FROM titulo_plataforma tp JOIN plataformas p ON p.id = tp.plataforma_id ORDER BY p.nome"""):
        plataformas_por_titulo.setdefault(r["titulo_id"], []).append(
            {"id": r["id"], "nome": r["nome"], "cor": r["cor"], "fonte": r["fonte"],
             "dublado": r["dublado"], "legendado": r["legendado"], "link": r["link"]})

    catalogo = []
    for r in con.execute("SELECT * FROM titulos ORDER BY titulo"):
        t = dict(r)
        t["generos"] = [g.strip() for g in (t["generos"] or "").split(",") if g.strip()]
        t["vibes"] = [VIBES_ANTIGAS.get(v.strip(), v.strip()) for v in (t["vibes"] or "").split(",") if v.strip()]
        t["plataformas"] = plataformas_por_titulo.get(t["id"], [])
        # dublado/legendado oficiais (catálogo do streaming); None = nenhuma plataforma informou
        oficiais = [p for p in t["plataformas"] if p["fonte"] == "streaming"]
        t["tem_dublado"] = any(p["dublado"] for p in oficiais) if oficiais else None
        t["tem_legenda"] = any(p["legendado"] for p in oficiais) if oficiais else None
        catalogo.append(t)
    return catalogo


def buscar_titulo(con, tid):
    r = con.execute("SELECT * FROM titulos WHERE id = ?", (tid,)).fetchone()
    return dict(r) if r else None


def plataformas_do_titulo(con, tid):
    return [dict(r) for r in con.execute(
        """SELECT p.*, tp.fonte, tp.dublado, tp.legendado, tp.qualidade, tp.link, tp.expira_em
           FROM plataformas p JOIN titulo_plataforma tp ON tp.plataforma_id = p.id
           WHERE tp.titulo_id = ? ORDER BY (tp.fonte = 'streaming') DESC, p.nome""", (tid,))]


# ------------------------------ Histórico ------------------------------
def listar_historico(con, uid):
    return [dict(r) for r in con.execute(
        """SELECT h.*, t.titulo, t.tipo, p.nome AS plataforma, p.cor
           FROM historico h
           JOIN titulos t ON t.id = h.titulo_id
           JOIN plataformas p ON p.id = h.plataforma_id
           WHERE h.usuario_id = ? ORDER BY h.data DESC, h.id DESC""", (uid,))]


def registrar_historico(con, uid, titulo_id, plataforma_id, data, minutos, audio=None):
    con.execute("INSERT INTO historico (usuario_id, titulo_id, plataforma_id, data, minutos, audio) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, titulo_id, plataforma_id, data, minutos, audio))
    con.commit()


def audios_confirmados(con, titulo_id=None):
    """Quantas pessoas diferentes assistiram cada título dublado ou legendado.

    Devolve {titulo_id: {"dublado": n, "legendado": n}}; com titulo_id, só o dicionário daquele título.
    """
    filtro, params = ("AND titulo_id = ?", (titulo_id,)) if titulo_id else ("", ())
    resultado = {}
    for r in con.execute(f"""SELECT titulo_id, audio, COUNT(DISTINCT usuario_id) AS pessoas FROM historico
                             WHERE audio IN ('dublado', 'legendado') {filtro} GROUP BY titulo_id, audio""", params):
        resultado.setdefault(r["titulo_id"], {})[r["audio"]] = r["pessoas"]
    return resultado.get(titulo_id, {}) if titulo_id else resultado
    con.commit()


def excluir_historico(con, uid, hid):
    con.execute("DELETE FROM historico WHERE id = ? AND usuario_id = ?", (hid, uid))
    con.commit()


def contar_catalogo(con):
    r = con.execute("""SELECT COUNT(*) AS total, SUM(origem = 'tmdb' OR tmdb_id IS NOT NULL) AS tmdb,
                              SUM(origem = 'streaming' OR id IN (SELECT titulo_id FROM titulo_plataforma WHERE fonte = 'streaming')) AS streaming,
                              SUM(tipo = 'filme') AS filmes, SUM(tipo = 'serie') AS series FROM titulos""").fetchone()
    return {k: (r[k] or 0) for k in ("total", "tmdb", "streaming", "filmes", "series")}


# ---------------------------------------------------------------- configurações
def ler_config(con, chave):
    r = con.execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave,)).fetchone()
    return r["valor"] if r else None


def salvar_config(con, chave, valor):
    con.execute("INSERT INTO configuracoes (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                (chave, valor))
    con.commit()


# ---------------------------------------------------------------- avaliações (RF09)
def avaliar(con, uid, titulo_id, nota, comentario):
    con.execute("""INSERT INTO avaliacoes (usuario_id, titulo_id, nota, comentario) VALUES (?, ?, ?, ?)
                   ON CONFLICT(usuario_id, titulo_id) DO UPDATE SET nota = excluded.nota,
                   comentario = excluded.comentario, criado_em = datetime('now')""",
                (uid, titulo_id, nota, comentario or None))
    con.commit()


def excluir_avaliacao(con, uid, titulo_id):
    con.execute("DELETE FROM avaliacoes WHERE usuario_id = ? AND titulo_id = ?", (uid, titulo_id))
    con.commit()


def avaliacao_do_usuario(con, uid, titulo_id):
    r = con.execute("SELECT * FROM avaliacoes WHERE usuario_id = ? AND titulo_id = ?", (uid, titulo_id)).fetchone()
    return dict(r) if r else None


def minhas_avaliacoes(con, uid):
    return [dict(r) for r in con.execute(
        """SELECT a.*, t.titulo, t.tipo, t.ano, t.poster_url FROM avaliacoes a JOIN titulos t ON t.id = a.titulo_id
           WHERE a.usuario_id = ? ORDER BY a.criado_em DESC, a.id DESC""", (uid,))]


def para_avaliar(con, uid):
    """Títulos que o usuário assistiu (histórico) e ainda não avaliou."""
    return [dict(r) for r in con.execute(
        """SELECT t.id, t.titulo, t.tipo, t.ano, t.poster_url, MAX(h.data) AS ultima_vez
           FROM historico h JOIN titulos t ON t.id = h.titulo_id
           WHERE h.usuario_id = ? AND t.id NOT IN (SELECT titulo_id FROM avaliacoes WHERE usuario_id = ?)
           GROUP BY t.id ORDER BY ultima_vez DESC""", (uid, uid))]


# ---------------------------------------------------------------- amizades (RF10)
_AMIGOS = """SELECT CASE WHEN solicitante_id = :u THEN destinatario_id ELSE solicitante_id END AS amigo_id
             FROM amizades WHERE status = 'aceita' AND (solicitante_id = :u OR destinatario_id = :u)"""


def situacao_amizade(con, uid, outro_id):
    """'amigos', 'enviado', 'recebido' ou None."""
    r = con.execute("""SELECT solicitante_id, status FROM amizades WHERE
                       (solicitante_id = ? AND destinatario_id = ?) OR (solicitante_id = ? AND destinatario_id = ?)""",
                    (uid, outro_id, outro_id, uid)).fetchone()
    if r is None:
        return None
    if r["status"] == "aceita":
        return "amigos"
    return "enviado" if r["solicitante_id"] == uid else "recebido"


def ids_amigos(con, uid):
    return {r["amigo_id"] for r in con.execute(_AMIGOS, {"u": uid})}


def listar_amigos(con, uid):
    return [dict(r) for r in con.execute(
        f"""SELECT u.id, u.nome, u.usuario, (SELECT COUNT(*) FROM avaliacoes a WHERE a.usuario_id = u.id) AS avaliacoes
            FROM usuarios u WHERE u.id IN ({_AMIGOS}) ORDER BY u.nome""", {"u": uid})]


def pedidos_recebidos(con, uid):
    return [dict(r) for r in con.execute(
        """SELECT am.id, u.nome, u.usuario FROM amizades am JOIN usuarios u ON u.id = am.solicitante_id
           WHERE am.destinatario_id = ? AND am.status = 'pendente' ORDER BY am.criado_em""", (uid,))]


def pedidos_enviados(con, uid):
    return [dict(r) for r in con.execute(
        """SELECT am.id, u.nome, u.usuario FROM amizades am JOIN usuarios u ON u.id = am.destinatario_id
           WHERE am.solicitante_id = ? AND am.status = 'pendente' ORDER BY am.criado_em""", (uid,))]


def solicitar_amizade(con, uid, usuario):
    """Envia um pedido de amizade pelo nome de usuário. Devolve (ok, mensagem)."""
    outro = buscar_usuario_por_usuario(con, usuario)
    if outro is None:
        return False, f"Não encontramos ninguém com o usuário @{usuario.strip().lstrip('@').lower()}."
    if outro["id"] == uid:
        return False, "Esse é o seu próprio usuário."
    if outro["id"] in ids_amigos(con, uid):
        return False, f"Você e {outro['nome']} já são amigos."
    inverso = con.execute("SELECT id FROM amizades WHERE solicitante_id = ? AND destinatario_id = ? AND status = 'pendente'",
                          (outro["id"], uid)).fetchone()
    if inverso:  # a outra pessoa já tinha pedido: aceita direto
        con.execute("UPDATE amizades SET status = 'aceita' WHERE id = ?", (inverso["id"],))
        con.commit()
        return True, f"Você e {outro['nome']} agora são amigos."
    if con.execute("SELECT 1 FROM amizades WHERE solicitante_id = ? AND destinatario_id = ?", (uid, outro["id"])).fetchone():
        return False, f"Você já enviou um pedido para {outro['nome']}."
    con.execute("INSERT INTO amizades (solicitante_id, destinatario_id) VALUES (?, ?)", (uid, outro["id"]))
    con.commit()
    return True, f"Pedido enviado para {outro['nome']}."


def responder_pedido(con, uid, pedido_id, aceitar):
    if aceitar:
        con.execute("UPDATE amizades SET status = 'aceita' WHERE id = ? AND destinatario_id = ? AND status = 'pendente'",
                    (pedido_id, uid))
    else:
        con.execute("DELETE FROM amizades WHERE id = ? AND destinatario_id = ? AND status = 'pendente'", (pedido_id, uid))
    con.commit()


def cancelar_pedido(con, uid, pedido_id):
    con.execute("DELETE FROM amizades WHERE id = ? AND solicitante_id = ? AND status = 'pendente'", (pedido_id, uid))
    con.commit()


def remover_amizade(con, uid, amigo_id):
    con.execute("""DELETE FROM amizades WHERE status = 'aceita' AND
                   ((solicitante_id = ? AND destinatario_id = ?) OR (solicitante_id = ? AND destinatario_id = ?))""",
                (uid, amigo_id, amigo_id, uid))
    con.commit()


def feed_amigos(con, uid, limite=40):
    """Avaliações mais recentes dos amigos."""
    return [dict(r) for r in con.execute(
        f"""SELECT a.*, u.nome, u.usuario, t.titulo, t.tipo, t.ano, t.poster_url FROM avaliacoes a
            JOIN usuarios u ON u.id = a.usuario_id JOIN titulos t ON t.id = a.titulo_id
            WHERE a.usuario_id IN ({_AMIGOS}) ORDER BY a.criado_em DESC, a.id DESC LIMIT :lim""",
        {"u": uid, "lim": limite})]


def avaliacoes_amigos_titulo(con, uid, titulo_id):
    return [dict(r) for r in con.execute(
        f"""SELECT a.*, u.nome, u.usuario FROM avaliacoes a JOIN usuarios u ON u.id = a.usuario_id
            WHERE a.titulo_id = :t AND a.usuario_id IN ({_AMIGOS}) ORDER BY a.criado_em DESC""",
        {"u": uid, "t": titulo_id})]


def notas_amigos(con, uid):
    """titulo_id -> (média, quantidade) das notas dos amigos."""
    return {r["titulo_id"]: (r["media"], r["qtd"]) for r in con.execute(
        f"""SELECT titulo_id, AVG(nota) AS media, COUNT(*) AS qtd FROM avaliacoes
            WHERE usuario_id IN ({_AMIGOS}) GROUP BY titulo_id""", {"u": uid})}
