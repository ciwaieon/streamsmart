"""
StreamSmart — Assista ao que importa, controle o que gasta.

Aplicação web em Python (Flask) + SQLite.
Projeto Integrador: Laboratório de Programação — UNISA.

Para executar:  python app.py   e abra http://127.0.0.1:5000
Usuário de demonstração: demo@streamsmart.com / demo123
"""
import calendar
import math
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import database
import repositorio as repo
from services import custos, recomendador, relatorio

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


@app.context_processor
def contexto_global():
    return {"usuario_nome": session.get("usuario_nome"), "ano_atual": hoje().year}


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
    return render_template("landing.html", vibes=recomendador.VIBES)


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        confirmar = request.form.get("confirmar", "")
        erros = []
        if len(nome) < 2:
            erros.append("Informe seu nome.")
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
            return render_template("cadastro.html", nome=nome, email=email), 400
        novo_id = repo.criar_usuario(db(), nome, email, generate_password_hash(senha))
        session.clear()
        session["usuario_id"], session["usuario_nome"] = novo_id, nome
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
        session["usuario_id"], session["usuario_nome"] = usuario["id"], usuario["nome"]
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


# ------------------------------------------------------------------ gráficos (SVG gerado no servidor)
def fatias_svg(fatias, raio=80, centro=100):
    """Converte percentuais em caminhos SVG de um gráfico de rosca/pizza."""
    resultado, angulo = [], -math.pi / 2
    for f in fatias:
        varredura = f["pct"] / 100 * 2 * math.pi
        if f["pct"] >= 99.999:
            caminho = (f"M {centro} {centro - raio} A {raio} {raio} 0 1 1 {centro - 0.01} {centro - raio} Z")
        else:
            x1, y1 = centro + raio * math.cos(angulo), centro + raio * math.sin(angulo)
            angulo2 = angulo + varredura
            x2, y2 = centro + raio * math.cos(angulo2), centro + raio * math.sin(angulo2)
            grande = 1 if varredura > math.pi else 0
            caminho = f"M {centro} {centro} L {x1:.2f} {y1:.2f} A {raio} {raio} 0 {grande} 1 {x2:.2f} {y2:.2f} Z"
        resultado.append({**f, "caminho": caminho})
        angulo += varredura
    return resultado


# ------------------------------------------------------------------ painel (dashboard)
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
    alertas = custos.alertas(assinaturas, d)
    ids_alerta = {al["assinatura"]["id"]: al for al in alertas}
    _, dias_mes = calendar.monthrange(d.year, d.month)
    return render_template(
        "painel.html",
        resumo=custos.resumo(assinaturas),
        mais_assistida=relatorio.mais_assistida(historico, d),
        assinaturas=assinaturas,
        alertas=alertas,
        ids_alerta=ids_alerta,
        fatias=fatias_svg(custos.fatias_pizza(assinaturas)),
        cobrancas=custos.cobrancas_do_mes(assinaturas, d),
        dias_mes=dias_mes, hoje=d, mes_nome=MESES[d.month - 1],
    )


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
@app.route("/recomendar")
@login_obrigatorio
def recomendar():
    assinadas = {a["plataforma"] for a in repo.listar_assinaturas(db(), uid())}
    buscou = "vibe" in request.args
    filtros = {
        "tempo": request.args.get("tempo", "90"),
        "vibe": request.args.get("vibe", "rir"),
        "companhia": request.args.get("companhia", "sozinho"),
        "somente_minhas": request.args.get("somente") == "1" if buscou else True,
    }
    resultados, total = [], 0
    if buscou:
        ja_vistos = {h["titulo_id"] for h in repo.listar_historico(db(), uid())}
        resultados, total = recomendador.recomendar(repo.listar_catalogo(db()), filtros, assinadas, ja_vistos)
    return render_template("recomendar.html", filtros=filtros, buscou=buscou, resultados=resultados, total=total,
                           tempos=recomendador.TEMPOS, vibes=recomendador.VIBES,
                           companhias=recomendador.COMPANHIAS, assinadas=assinadas)


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
        except (KeyError, ValueError) as e:
            flash(str(e) if str(e) and not str(e).startswith("invalid") else "Dados inválidos.", "erro")
            return redirect(request.form.get("voltar") or url_for("historico"))
        repo.registrar_historico(db(), uid(), titulo_id, plataforma_id, data, minutos)
        flash(f"“{titulo['titulo']}” registrado no seu histórico.", "sucesso")
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


if __name__ == "__main__":
    database.inicializar()
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
