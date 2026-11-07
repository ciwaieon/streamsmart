"""
StreamSmart — Assista ao que importa, controle o que gasta.

Aplicação web em Python (Flask) + SQLite.
Projeto Integrador: Laboratório de Programação — UNISA.

Para executar:  python app.py   e abra http://127.0.0.1:5000
Usuário de demonstração: demo@streamsmart.com / demo123
"""
import math
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import database
import repositorio as repo
from services import categorias, custos, recomendador, relatorio
from services import importador
from services.tmdb import ClienteTMDB, ErroTMDB

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("STREAMSMART_SECRET", "troque-esta-chave-em-producao")

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


def hoje():
    return date.today()


# ------------------------------------------------------------------ banco
def db():
    if "db" not in g:
        g.db = database.conectar(app.config.get("DATABASE"))
    return g.db


@app.teardown_appcontext
def fechar_db(_erro):
    con = g.pop("db", None)
    if con is not None:
        con.close()


# ------------------------------------------------------------------ filtros de template
@app.template_filter("moeda")
def moeda(valor):
    """Formata no padrão brasileiro: R$ 1.234,56"""
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


@app.template_filter("data_br")
def data_br(valor):
    if isinstance(valor, str):
        valor = date.fromisoformat(valor)
    return valor.strftime("%d/%m/%Y")


@app.template_filter("duracao")
def duracao(minutos):
    h, m = divmod(int(minutos), 60)
    if h and m:
        return f"{h}h{m:02d}"
    return f"{h}h" if h else f"{m} min"


@app.template_filter("iniciais")
def iniciais(texto):
    palavras = [p for p in texto.replace(":", " ").split() if p[0].isalnum()]
    return "".join(p[0] for p in palavras[:2]).upper()


@app.template_filter("texto_sobre")
def texto_sobre(cor):
    """Escolhe texto escuro ou claro para ficar legível sobre a cor da plataforma (luminância relativa)."""
    try:
        r, g, b = (int(cor.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, AttributeError):
        return "#fff"
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    luminancia = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    return "#16171B" if luminancia > 0.28 else "#fff"


@app.template_filter("estrelas")
def estrelas(nota):
    nota = int(round(nota or 0))
    return "★" * nota + "☆" * (5 - nota)


@app.template_filter("decimal")
def decimal_br(valor, casas=1):
    return f"{valor:.{casas}f}".replace(".", ",")


@app.context_processor
def contexto_global():
    pedidos = 0
    if "usuario_id" in session:
        pedidos = len(repo.pedidos_recebidos(db(), session["usuario_id"]))
    return {"usuario_nome": session.get("usuario_nome"), "usuario_arroba": session.get("usuario_arroba"),
            "ano_atual": hoje().year, "pedidos_pendentes": pedidos,
            "classificacoes": categorias.DESCRICAO_CLASSIFICACAO, "nome_idioma": categorias.nome_idioma}


# ------------------------------------------------------------------ autenticação (RF01)
def login_obrigatorio(view):
    @wraps(view)
    def envolvida(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Entre na sua conta para continuar.", "aviso")
            return redirect(url_for("login", proximo=request.path))
        return view(*args, **kwargs)
    return envolvida


def uid():
    return session["usuario_id"]


@app.route("/")
def landing():
    if "usuario_id" in session:
        return redirect(url_for("painel"))
    return render_template("landing.html", vibes=categorias.VIBES)


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        usuario = request.form.get("usuario", "").strip().lstrip("@").lower()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        confirmar = request.form.get("confirmar", "")
        erros = []
        if len(nome) < 2:
            erros.append("Informe seu nome.")
        if not re.fullmatch(r"[a-z0-9_.]{3,20}", usuario):
            erros.append("O nome de usuário deve ter de 3 a 20 caracteres: letras sem acento, números, ponto ou _.")
        elif repo.buscar_usuario_por_usuario(db(), usuario):
            erros.append(f"O usuário @{usuario} já existe. Escolha outro.")
        if "@" not in email or "." not in email.split("@")[-1]:
            erros.append("Informe um e-mail válido.")
        if len(senha) < 6:
            erros.append("A senha deve ter pelo menos 6 caracteres.")
        if senha != confirmar:
            erros.append("As senhas não conferem.")
        if not erros and repo.buscar_usuario_por_email(db(), email):
            erros.append("Já existe uma conta com esse e-mail.")
        if erros:
            for e in erros:
                flash(e, "erro")
            return render_template("cadastro.html", nome=nome, email=email, usuario=usuario), 400
        novo_id = repo.criar_usuario(db(), nome, email, generate_password_hash(senha), usuario)
        session.clear()
        session["usuario_id"], session["usuario_nome"], session["usuario_arroba"] = novo_id, nome, usuario
        flash("Conta criada! Comece cadastrando seus streamings.", "sucesso")
        return redirect(url_for("assinaturas"))
    return render_template("cadastro.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "")
        senha = request.form.get("senha", "")
        usuario = repo.buscar_usuario_por_email(db(), email)
        if usuario is None or not check_password_hash(usuario["senha_hash"], senha):
            flash("E-mail ou senha incorretos.", "erro")
            return render_template("login.html", email=email), 401
        session.clear()
        session["usuario_id"], session["usuario_nome"], session["usuario_arroba"] = usuario["id"], usuario["nome"], usuario["usuario"]
        proximo = request.args.get("proximo", "")
        return redirect(proximo if proximo.startswith("/") and not proximo.startswith("//") else url_for("painel"))
    return render_template("login.html")


@app.route("/sair")
def sair():
    session.clear()
    flash("Você saiu da sua conta.", "sucesso")
    return redirect(url_for("landing"))


@app.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    """Recuperação de senha. Em produção o link seria enviado por e-mail;
    neste protótipo ele é exibido na tela (envio de e-mail simulado)."""
    link = None
    if request.method == "POST":
        usuario = repo.buscar_usuario_por_email(db(), request.form.get("email", ""))
        if usuario:
            token = secrets.token_urlsafe(24)
            expira = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
            repo.salvar_token(db(), usuario["id"], token, expira)
            link = url_for("redefinir", token=token, _external=True)
        # Mensagem igual nos dois casos para não revelar quais e-mails existem
        flash("Se o e-mail estiver cadastrado, enviamos um link de redefinição válido por 1 hora.", "sucesso")
    return render_template("recuperar.html", link=link)


@app.route("/redefinir/<token>", methods=["GET", "POST"])
def redefinir(token):
    registro = repo.buscar_token_valido(db(), token, datetime.now().isoformat(timespec="seconds"))
    if registro is None:
        flash("Link inválido ou expirado. Peça um novo.", "erro")
        return redirect(url_for("recuperar"))
    if request.method == "POST":
        senha = request.form.get("senha", "")
        if len(senha) < 6 or senha != request.form.get("confirmar", ""):
            flash("A senha deve ter 6+ caracteres e as duas devem ser iguais.", "erro")
            return render_template("redefinir.html", token=token), 400
        repo.atualizar_senha(db(), registro["usuario_id"], generate_password_hash(senha))
        repo.marcar_token_usado(db(), registro["id"])
        flash("Senha alterada. Entre com a nova senha.", "sucesso")
        return redirect(url_for("login"))
    return render_template("redefinir.html", token=token)


# ------------------------------------------------------------------ painel (início)
# Plataformas tratadas no feminino, para as frases saírem em bom português ("da Netflix", "do Prime Video")
FEMININAS = {"Netflix", "HBO Max", "Apple TV+"}


def de(plataforma):
    return ("da " if plataforma in FEMININAS else "do ") + plataforma


@app.route("/painel")
@login_obrigatorio
def painel():
    d = hoje()
    assinaturas = repo.listar_assinaturas(db(), uid())
    historico = repo.listar_historico(db(), uid())
    for a in assinaturas:
        a["valor_mensal"] = custos.valor_mensal(a)
        a["proximo"] = custos.proximo_vencimento(a, d)
        a["dias"] = (a["proximo"] - d).days
    resumo = custos.resumo(assinaturas)
    analise = relatorio.analisar(assinaturas, historico, d)

    # extrato: cada assinatura com custo, uso e custo por hora, da mais cara para a mais barata
    max_horas = max([l["horas"] for l in analise["linhas"]] + [1])
    extrato = sorted(analise["linhas"], key=lambda l: -l["custo_mensal"])
    for l in extrato:
        l["uso_pct"] = round(l["horas"] / max_horas * 100)

    # no máximo 2 avisos, do mais importante para o menos: assinatura parada, depois a próxima cobrança
    notas = []
    for l in analise["linhas"]:
        if l["status"] == "pausar":
            p, dias = l["assinatura"]["plataforma"], l["dias_sem_uso"]
            if dias is None:
                parado = "sem nenhum uso registrado"
            elif dias >= 60:
                parado = f"sem uso há {dias // 30} meses"
            else:
                parado = f"sem uso há {dias} dias"
            notas.append({"cor": l["assinatura"]["cor"], "link": url_for("relatorio_view"), "acao": "Ver custo-benefício",
                          "texto": f"{p} {parado}: pausar economiza {moeda(l['custo_mensal'] * 12)} por ano."})
            break
    for al in custos.alertas(assinaturas, d):
        a = al["assinatura"]
        quando = "hoje" if al["dias"] == 0 else ("amanhã" if al["dias"] == 1 else f"em {al['dias']} dias")
        texto = (f"Teste grátis {de(a['plataforma'])} termina {quando}." if al["tipo"] == "teste"
                 else f"{a['plataforma']} renova {quando}, {moeda(a['valor'])}.")
        notas.append({"cor": a["cor"], "texto": texto})
        break
    notas = notas[:2]

    # faixa do mês: proporção de cada plataforma no gasto
    total = resumo["total_mensal"] or 1
    faixa = [{"nome": a["plataforma"], "cor": a["cor"], "valor": a["valor_mensal"], "pct": a["valor_mensal"] / total * 100}
             for a in sorted(assinaturas, key=lambda a: -a["valor_mensal"]) if a["valor_mensal"] > 0]

    # para hoje à noite: o que mais combina, só nas assinaturas do usuário, sem repetir o já visto
    assinadas = {a["plataforma"] for a in assinaturas}
    vistos = {h["titulo_id"] for h in historico}
    sugestoes = []
    if assinadas:
        candidatos = recomendador.recomendar(
            repo.listar_catalogo(db()),
            {"tempo": "livre", "vibes": [], "companhia": "sozinho", "classificacao_max": "18", "somente_minhas": True,
             "ordenar": "compat"},
            assinadas, vistos, repo.notas_amigos(db(), uid()))
        sugestoes = [c for c in candidatos if c["id"] not in vistos][:6]

    return render_template("painel.html", resumo=resumo, assinaturas=assinaturas, extrato=extrato, notas=notas,
                           faixa=faixa, sugestoes=sugestoes, mes_nome=MESES[d.month - 1], hoje=d)


# ------------------------------------------------------------------ assinaturas (RF02)
def _ler_form_assinatura(form):
    """Valida o formulário e devolve (dados, erros)."""
    erros, dados = [], {}
    plataformas = {p["id"] for p in repo.listar_plataformas(db())}
    try:
        dados["plataforma_id"] = int(form.get("plataforma_id", ""))
        if dados["plataforma_id"] not in plataformas:
            raise ValueError
    except ValueError:
        erros.append("Escolha uma plataforma.")
    dados["plano"] = form.get("plano", "").strip() or "Padrão"
    try:
        dados["valor"] = round(float(form.get("valor", "").replace("R$", "").replace(",", ".").strip()), 2)
        if dados["valor"] < 0:
            raise ValueError
    except ValueError:
        erros.append("Informe um valor válido (ex.: 39,90).")
    dados["periodicidade"] = form.get("periodicidade", "mensal")
    if dados["periodicidade"] not in ("mensal", "anual"):
        erros.append("Periodicidade inválida.")
    try:
        dados["dia_vencimento"] = int(form.get("dia_vencimento", ""))
        if not 1 <= dados["dia_vencimento"] <= 31:
            raise ValueError
    except ValueError:
        erros.append("O dia do vencimento deve estar entre 1 e 31.")
    dados["mes_vencimento"] = None
    if dados["periodicidade"] == "anual":
        try:
            dados["mes_vencimento"] = int(form.get("mes_vencimento", ""))
            if not 1 <= dados["mes_vencimento"] <= 12:
                raise ValueError
        except ValueError:
            erros.append("Para plano anual, informe o mês da renovação.")
    dados["fim_teste"] = form.get("fim_teste", "").strip() or None
    if dados["fim_teste"]:
        try:
            date.fromisoformat(dados["fim_teste"])
        except ValueError:
            erros.append("Data de fim do teste inválida.")
    return dados, erros


@app.route("/assinaturas")
@login_obrigatorio
def assinaturas():
    d = hoje()
    lista = repo.listar_assinaturas(db(), uid())
    for a in lista:
        a["valor_mensal"] = custos.valor_mensal(a)
        a["proximo"] = custos.proximo_vencimento(a, d)
        a["dias"] = (a["proximo"] - d).days
    return render_template("assinaturas.html", assinaturas=lista, resumo=custos.resumo(lista),
                           ids_alerta={al["assinatura"]["id"]: al for al in custos.alertas(lista, d)})


@app.route("/assinaturas/nova", methods=["GET", "POST"])
@login_obrigatorio
def nova_assinatura():
    if request.method == "POST":
        dados, erros = _ler_form_assinatura(request.form)
        if not erros:
            try:
                repo.criar_assinatura(db(), uid(), dados)
                flash("Assinatura cadastrada.", "sucesso")
                return redirect(url_for("assinaturas"))
            except sqlite3.IntegrityError:
                erros.append("Você já cadastrou essa plataforma. Edite a assinatura existente.")
        for e in erros:
            flash(e, "erro")
        return render_template("assinatura_form.html", a=request.form, plataformas=repo.listar_plataformas(db()),
                               meses=MESES, editando=False), 400
    return render_template("assinatura_form.html", a={}, plataformas=repo.listar_plataformas(db()),
                           meses=MESES, editando=False)


@app.route("/assinaturas/<int:aid>/editar", methods=["GET", "POST"])
@login_obrigatorio
def editar_assinatura(aid):
    atual = repo.buscar_assinatura(db(), uid(), aid)
    if atual is None:
        flash("Assinatura não encontrada.", "erro")
        return redirect(url_for("assinaturas"))
    if request.method == "POST":
        dados, erros = _ler_form_assinatura(request.form)
        if not erros:
            try:
                repo.atualizar_assinatura(db(), uid(), aid, dados)
                flash("Assinatura atualizada.", "sucesso")
                return redirect(url_for("assinaturas"))
            except sqlite3.IntegrityError:
                erros.append("Você já tem outra assinatura dessa plataforma.")
        for e in erros:
            flash(e, "erro")
        return render_template("assinatura_form.html", a=request.form, plataformas=repo.listar_plataformas(db()),
                               meses=MESES, editando=True, aid=aid), 400
    return render_template("assinatura_form.html", a=atual, plataformas=repo.listar_plataformas(db()),
                           meses=MESES, editando=True, aid=aid)


@app.route("/assinaturas/<int:aid>/excluir", methods=["POST"])
@login_obrigatorio
def excluir_assinatura(aid):
    repo.excluir_assinatura(db(), uid(), aid)
    flash("Assinatura removida.", "sucesso")
    return redirect(url_for("assinaturas"))


# ------------------------------------------------------------------ recomendador (RF05, RF06)
POR_PAGINA = 24


@app.route("/recomendar")
@login_obrigatorio
def recomendar():
    assinadas = {a["plataforma"] for a in repo.listar_assinaturas(db(), uid())}
    buscou = "tempo" in request.args
    a = request.args
    filtros = {
        "tempo": a.get("tempo", "90"),
        "vibes": [v for v in a.getlist("vibe") if v in categorias.VIBES][:3],
        "categorias": [c for c in a.getlist("categoria") if c in categorias.CATEGORIAS],
        "idiomas": [i for i in a.getlist("idioma") if i in dict(categorias.FILTRO_IDIOMAS)],
        "audio": [x for x in a.getlist("audio") if x in ("dublado", "legendado")],
        "tipo": a.get("tipo", "todos"),
        "classificacao_max": a.get("classificacao", "18") if a.get("classificacao") in categorias.CLASSIFICACOES else "18",
        "companhia": a.get("companhia", "sozinho") if a.get("companhia") in recomendador.COMPANHIAS else "sozinho",
        "plataformas": a.getlist("plataforma"),
        "somente_minhas": a.get("somente") == "1" if buscou else True,
        "ordenar": a.get("ordenar", "compat") if a.get("ordenar") in recomendador.ORDENACOES else "compat",
    }
    resultados, total, pagina, paginas = [], 0, 1, 1
    if buscou:
        ja_vistos = {h["titulo_id"] for h in repo.listar_historico(db(), uid())}
        catalogo_completo = repo.listar_catalogo(db())
        # onde a plataforma não informou o áudio, vale o que os usuários registraram ao assistir
        comunidade = repo.audios_confirmados(db())
        for t in catalogo_completo:
            c = comunidade.get(t["id"], {})
            if not t["tem_dublado"] and c.get("dublado"):
                t["tem_dublado"] = "comunidade"
            if not t["tem_legenda"] and c.get("legendado"):
                t["tem_legenda"] = "comunidade"
            if t.get("idioma_original") == "pt":
                t["tem_dublado"] = t["tem_dublado"] or "nacional"
        todos = recomendador.recomendar(catalogo_completo, filtros, assinadas, ja_vistos,
                                        repo.notas_amigos(db(), uid()))
        total = len(todos)
        paginas = max(1, math.ceil(total / POR_PAGINA))
        try:
            pagina = min(max(int(a.get("pagina", 1)), 1), paginas)
        except ValueError:
            pagina = 1
        resultados = todos[(pagina - 1) * POR_PAGINA: pagina * POR_PAGINA]

    def link_pagina(n):
        args = a.to_dict(flat=False)
        args["pagina"] = [str(n)]
        return url_for("recomendar", **args) + "#resultados"

    return render_template(
        "recomendar.html", filtros=filtros, buscou=buscou, resultados=resultados, total=total,
        idiomas=categorias.FILTRO_IDIOMAS,
        importacao=importador.status(db()),
        pagina=pagina, paginas=paginas, link_pagina=link_pagina,
        tempos=categorias.TEMPOS, vibes=categorias.VIBES, lista_categorias=categorias.CATEGORIAS,
        companhias=recomendador.COMPANHIAS, tipos=recomendador.TIPOS, ordenacoes=recomendador.ORDENACOES,
        plataformas=repo.listar_plataformas(db()), assinadas=assinadas, catalogo=repo.contar_catalogo(db()))


# ------------------------------------------------------------------ página do título e avaliações (RF09)
@app.route("/titulo/<int:tid>")
@login_obrigatorio
def titulo(tid):
    t = repo.buscar_titulo(db(), tid)
    if t is None:
        flash("Título não encontrado.", "erro")
        return redirect(url_for("recomendar"))
    t["generos"] = [g for g in (t["generos"] or "").split(",") if g]
    t["plataformas"] = repo.plataformas_do_titulo(db(), tid)
    dos_amigos = repo.avaliacoes_amigos_titulo(db(), uid(), tid)
    media = sum(x["nota"] for x in dos_amigos) / len(dos_amigos) if dos_amigos else None
    vezes = [h for h in repo.listar_historico(db(), uid()) if h["titulo_id"] == tid]
    assinadas = {x["plataforma"] for x in repo.listar_assinaturas(db(), uid())}
    return render_template("titulo.html", t=t, minha=repo.avaliacao_do_usuario(db(), uid(), tid),
                           audio=repo.audios_confirmados(db(), tid),
                           dos_amigos=dos_amigos, media_amigos=media, vezes=vezes, assinadas=assinadas,
                           hoje=hoje().isoformat())


@app.route("/titulo/<int:tid>/avaliar", methods=["POST"])
@login_obrigatorio
def avaliar(tid):
    if repo.buscar_titulo(db(), tid) is None:
        flash("Título não encontrado.", "erro")
        return redirect(url_for("avaliacoes"))
    try:
        nota = int(request.form.get("nota", ""))
        if not 1 <= nota <= 5:
            raise ValueError
    except ValueError:
        flash("Escolha uma nota de 1 a 5 estrelas.", "erro")
        return redirect(url_for("titulo", tid=tid))
    comentario = request.form.get("comentario", "").strip()[:500]
    repo.avaliar(db(), uid(), tid, nota, comentario)
    flash("Avaliação salva. Seus amigos já podem ver.", "sucesso")
    voltar = request.form.get("voltar", "")
    return redirect(voltar if voltar.startswith("/") and not voltar.startswith("//") else url_for("titulo", tid=tid))


@app.route("/titulo/<int:tid>/avaliacao/excluir", methods=["POST"])
@login_obrigatorio
def excluir_avaliacao(tid):
    repo.excluir_avaliacao(db(), uid(), tid)
    flash("Avaliação removida.", "sucesso")
    return redirect(url_for("titulo", tid=tid))


@app.route("/avaliacoes")
@login_obrigatorio
def avaliacoes():
    return render_template("avaliacoes.html", pendentes=repo.para_avaliar(db(), uid()),
                           minhas=repo.minhas_avaliacoes(db(), uid()))


# ------------------------------------------------------------------ amigos (RF10)
@app.route("/amigos")
@login_obrigatorio
def amigos():
    busca = request.args.get("busca", "").strip()
    encontrados = repo.buscar_pessoas(db(), uid(), busca) if busca else []
    for p in encontrados:
        p["situacao"] = repo.situacao_amizade(db(), uid(), p["id"])
    return render_template("amigos.html", amigos=repo.listar_amigos(db(), uid()),
                           recebidos=repo.pedidos_recebidos(db(), uid()), enviados=repo.pedidos_enviados(db(), uid()),
                           feed=repo.feed_amigos(db(), uid()), busca=busca, encontrados=encontrados)


@app.route("/amigos/adicionar", methods=["POST"])
@login_obrigatorio
def adicionar_amigo():
    ok, msg = repo.solicitar_amizade(db(), uid(), request.form.get("usuario", ""))
    flash(msg, "sucesso" if ok else "erro")
    busca = request.form.get("busca", "")
    return redirect(url_for("amigos", busca=busca) if busca else url_for("amigos"))


@app.route("/amigos/pedido/<int:pid>/<acao>", methods=["POST"])
@login_obrigatorio
def responder_pedido(pid, acao):
    if acao == "cancelar":
        repo.cancelar_pedido(db(), uid(), pid)
        flash("Pedido cancelado.", "sucesso")
    else:
        repo.responder_pedido(db(), uid(), pid, acao == "aceitar")
        flash("Pedido aceito." if acao == "aceitar" else "Pedido recusado.", "sucesso")
    return redirect(url_for("amigos"))


@app.route("/amigos/<int:amigo_id>/remover", methods=["POST"])
@login_obrigatorio
def remover_amigo(amigo_id):
    repo.remover_amizade(db(), uid(), amigo_id)
    flash("Amizade desfeita.", "sucesso")
    return redirect(url_for("amigos"))


# ------------------------------------------------------------------ catálogo TMDB
@app.route("/catalogo", methods=["GET", "POST"])
@login_obrigatorio
def catalogo():
    """Página técnica (fora do menu): mostra o andamento da importação automática do TMDB."""
    if request.method == "POST":
        if request.form.get("acao") == "salvar":
            nova = request.form.get("chave", "").strip()
            try:
                ClienteTMDB(nova).testar()
            except ErroTMDB as e:
                flash(str(e), "erro")
                return redirect(url_for("catalogo"))
            repo.salvar_config(db(), "tmdb_chave", nova)
            flash("Chave conferida e salva. A importação começou em segundo plano.", "sucesso")
        else:
            flash("Atualização do catálogo iniciada em segundo plano.", "sucesso")
        if not app.config.get("TESTING"):
            importador.iniciar_em_segundo_plano(app.config.get("DATABASE"), forcar=True)
        return redirect(url_for("catalogo"))
    return render_template("catalogo.html", tem_chave=bool(importador.obter_chave(db())),
                           contagem=repo.contar_catalogo(db()), importacao=importador.status(db()))


# ------------------------------------------------------------------ histórico (RF07)
@app.route("/historico", methods=["GET", "POST"])
@login_obrigatorio
def historico():
    if request.method == "POST":
        try:
            titulo_id = int(request.form["titulo_id"])
            plataforma_id = int(request.form["plataforma_id"])
            titulo = repo.buscar_titulo(db(), titulo_id)
            if titulo is None:
                raise ValueError("Título não encontrado.")
            if plataforma_id not in {p["id"] for p in repo.plataformas_do_titulo(db(), titulo_id)}:
                raise ValueError("Esse título não está nessa plataforma.")
            data = request.form.get("data") or hoje().isoformat()
            if date.fromisoformat(data) > hoje():
                raise ValueError("A data não pode estar no futuro.")
            minutos = int(request.form.get("minutos") or titulo["duracao_min"])
            if minutos <= 0:
                raise ValueError("Informe os minutos assistidos.")
            audio = request.form.get("audio") or None
            if audio not in (None, "dublado", "legendado", "original"):
                raise ValueError("Escolha como você assistiu: dublado, legendado ou original.")
        except (KeyError, ValueError) as e:
            flash(str(e) if str(e) and not str(e).startswith("invalid") else "Dados inválidos.", "erro")
            return redirect(request.form.get("voltar") or url_for("historico"))
        repo.registrar_historico(db(), uid(), titulo_id, plataforma_id, data, minutos, audio)
        flash(f"“{titulo['titulo']}” entrou no seu histórico. Que tal avaliar?", "sucesso")
        voltar = request.form.get("voltar", "")
        return redirect(voltar if voltar.startswith("/") and not voltar.startswith("//") else url_for("historico"))

    return render_template("historico.html", historico=repo.listar_historico(db(), uid()),
                           catalogo=repo.listar_catalogo(db()), hoje=hoje().isoformat())


@app.route("/historico/<int:hid>/excluir", methods=["POST"])
@login_obrigatorio
def excluir_historico(hid):
    repo.excluir_historico(db(), uid(), hid)
    flash("Registro removido.", "sucesso")
    return redirect(url_for("historico"))


# ------------------------------------------------------------------ relatório (RF08)
@app.route("/relatorio")
@login_obrigatorio
def relatorio_view():
    analise = relatorio.analisar(repo.listar_assinaturas(db(), uid()), repo.listar_historico(db(), uid()), hoje())
    return render_template("relatorio.html", r=analise)


_importacao_disparada = False


@app.before_request
def importar_catalogo_automaticamente():
    """Na primeira requisição, confere se o catálogo do TMDB precisa ser atualizado (em segundo plano)."""
    global _importacao_disparada
    if not _importacao_disparada and not app.config.get("TESTING"):
        _importacao_disparada = True
        importador.iniciar_em_segundo_plano(app.config.get("DATABASE"))


if __name__ == "__main__":
    database.inicializar()
    importador.iniciar_em_segundo_plano()
    _importacao_disparada = True
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
