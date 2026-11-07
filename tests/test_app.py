"""Testes de integração: rotas do Flask com um banco SQLite temporário."""
import re

import pytest

import app as aplicacao
import database


@pytest.fixture
def cliente(tmp_path):
    caminho = str(tmp_path / "teste.db")
    database.inicializar(caminho, com_demo=True)
    aplicacao.app.config.update(TESTING=True, DATABASE=caminho)
    with aplicacao.app.test_client() as c:
        yield c


def entrar(c, email="demo@streamsmart.com", senha="demo123"):
    return c.post("/login", data={"email": email, "senha": senha})


def test_paginas_protegidas_exigem_login(cliente):
    for rota in ("/painel", "/assinaturas", "/recomendar", "/historico", "/relatorio"):
        r = cliente.get(rota)
        assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_login_invalido(cliente):
    r = entrar(cliente, senha="errada")
    assert r.status_code == 401
    assert "incorretos" in r.get_data(as_text=True)


def test_cadastro_e_validacoes(cliente):
    r = cliente.post("/cadastro", data={"nome": "Ana", "usuario": "ana.x", "email": "ana@x.com", "senha": "123", "confirmar": "123"})
    assert r.status_code == 400
    r = cliente.post("/cadastro", data={"nome": "Ana", "usuario": "Á!", "email": "ana@x.com", "senha": "segredo1", "confirmar": "segredo1"})
    assert "nome de usuário deve ter" in r.get_data(as_text=True)
    r = cliente.post("/cadastro", data={"nome": "Ana", "usuario": "@Ana.X", "email": "ana@x.com", "senha": "segredo1", "confirmar": "segredo1"})
    assert r.status_code == 302
    cliente.get("/sair")
    r = cliente.post("/cadastro", data={"nome": "Ana", "usuario": "ana.x", "email": "outra@x.com", "senha": "segredo1", "confirmar": "segredo1"})
    assert "@ana.x já existe" in r.get_data(as_text=True)
    r = cliente.post("/cadastro", data={"nome": "Ana", "usuario": "ana.y", "email": "ana@x.com", "senha": "segredo1", "confirmar": "segredo1"})
    assert "Já existe" in r.get_data(as_text=True)


def test_painel_mostra_totais_do_demo(cliente):
    entrar(cliente)
    html = cliente.get("/painel").get_data(as_text=True)
    assert "R$ 135,60</span> nos seus streamings" in html          # 44,90 + 29,90 + 46,90 + 166,80/12 + 0
    assert "R$ 1.627,20 por ano" in html
    assert "HBO Max sem uso há 2 meses" in html and "R$ 358,80 por ano" in html      # aviso mais importante
    assert "Netflix renova em 2 dias" in html                             # próxima cobrança
    assert "Teste grátis" not in html.split("Para hoje")[0]               # no máximo 2 avisos
    assert "Para hoje à noite" in html


def test_crud_de_assinatura(cliente):
    entrar(cliente)
    # cria (Globoplay = id 5 na ordem do JSON)
    r = cliente.post("/assinaturas/nova", data={"plataforma_id": "5", "plano": "Padrão", "valor": "22,90",
                                                "periodicidade": "mensal", "dia_vencimento": "15"})
    assert r.status_code == 302
    html = cliente.get("/assinaturas").get_data(as_text=True)
    assert "Globoplay" in html and "R$ 22,90" in html
    aid = int(re.search(r'/assinaturas/(\d+)/editar">Editar</a>\s*<form method="post" action="/assinaturas/\d+/excluir"\s*'
                        r'onsubmit="return confirm\(\'Remover a assinatura de Globoplay', html).group(1))
    # duplicada
    r = cliente.post("/assinaturas/nova", data={"plataforma_id": "5", "valor": "10", "periodicidade": "mensal",
                                                "dia_vencimento": "1"})
    assert "já cadastrou" in r.get_data(as_text=True)
    # valor inválido
    r = cliente.post(f"/assinaturas/{aid}/editar", data={"plataforma_id": "5", "valor": "abc",
                                                          "periodicidade": "mensal", "dia_vencimento": "15"})
    assert r.status_code == 400
    # anual sem mês
    r = cliente.post(f"/assinaturas/{aid}/editar", data={"plataforma_id": "5", "valor": "200",
                                                          "periodicidade": "anual", "dia_vencimento": "15"})
    assert "mês da renovação" in r.get_data(as_text=True)
    # edita
    r = cliente.post(f"/assinaturas/{aid}/editar", data={"plataforma_id": "5", "plano": "Premium", "valor": "39.90",
                                                          "periodicidade": "mensal", "dia_vencimento": "20"})
    assert r.status_code == 302
    assert "Premium" in cliente.get("/assinaturas").get_data(as_text=True)
    # remove
    cliente.post(f"/assinaturas/{aid}/excluir")
    assert "Globoplay" not in cliente.get("/assinaturas").get_data(as_text=True)


def test_usuario_nao_acessa_assinatura_de_outro(cliente):
    cliente.post("/cadastro", data={"nome": "Bia", "usuario": "bia", "email": "bia@x.com", "senha": "segredo1", "confirmar": "segredo1"})
    r = cliente.get("/assinaturas/1/editar")   # assinatura do usuário demo
    assert r.status_code == 302
    cliente.post("/assinaturas/1/excluir")
    cliente.get("/sair")
    entrar(cliente)
    assert "Netflix" in cliente.get("/assinaturas").get_data(as_text=True)


def test_recomendador_respeita_filtros(cliente):
    entrar(cliente)
    html = cliente.get("/recomendar?tempo=30&vibe=relaxar&companhia=criancas&classificacao=18&somente=1").get_data(as_text=True)
    assert "Bluey" in html
    assert "Stranger Things" not in html
    assert "Fora da sua assinatura" not in html

    def total(url):
        return int(re.search(r"(\d+) títulos? para você", cliente.get(url).get_data(as_text=True)).group(1))
    com_filtro = total("/recomendar?tempo=livre&vibe=emocao&companhia=sozinho&classificacao=18&somente=1")
    sem_filtro = total("/recomendar?tempo=livre&vibe=emocao&companhia=sozinho&classificacao=18")
    assert sem_filtro > com_filtro   # sem o filtro entram títulos de plataformas não assinadas
    assert total("/recomendar?tempo=livre&companhia=sozinho&classificacao=18&plataforma=Globoplay") >= 1
    assert total("/recomendar?tempo=livre&companhia=sozinho&classificacao=18&categoria=terror") <= 3


def test_recomendador_pagina_os_resultados(cliente):
    entrar(cliente)
    html = cliente.get("/recomendar?tempo=livre&companhia=sozinho&classificacao=18").get_data(as_text=True)
    assert "69 títulos para você" in html and "página 1 de 3" in html
    assert html.count('class="filme"') == 24
    html = cliente.get("/recomendar?tempo=livre&companhia=sozinho&classificacao=18&pagina=3").get_data(as_text=True)
    assert html.count('class="filme"') == 69 - 48


def test_avaliar_titulo_e_ver_amigos(cliente):
    entrar(cliente)
    tid = re.search(r'<option value="(\d+)"[^>]*>Ted Lasso</option>', cliente.get("/historico").get_data(as_text=True)).group(1)
    html = cliente.get(f"/titulo/{tid}").get_data(as_text=True)
    assert "Ana Souza" in html and "A série mais gentil" in html      # nota de uma amiga aparece
    assert cliente.post(f"/titulo/{tid}/avaliar", data={"nota": "9"}).status_code == 302
    assert "Escolha uma nota" in cliente.get(f"/titulo/{tid}").get_data(as_text=True)
    cliente.post(f"/titulo/{tid}/avaliar", data={"nota": "4", "comentario": "Muito bom"})
    html = cliente.get("/avaliacoes").get_data(as_text=True)
    assert "Ted Lasso" in html and "Muito bom" in html
    cliente.post(f"/titulo/{tid}/avaliar", data={"nota": "5", "comentario": "Melhor ainda"})   # atualiza, não duplica
    assert cliente.get("/avaliacoes").get_data(as_text=True).count("Melhor ainda") == 1
    # amigos veem a avaliação no feed
    cliente.get("/sair")
    entrar(cliente, "ana@streamsmart.com", "ana12345")
    assert "Melhor ainda" in cliente.get("/amigos").get_data(as_text=True)


def test_fluxo_de_amizade_por_nome_de_usuario(cliente):
    cliente.post("/cadastro", data={"nome": "Davi Rocha", "usuario": "davi.r", "email": "davi@x.com", "senha": "segredo1", "confirmar": "segredo1"})
    r = cliente.post("/amigos/adicionar", data={"usuario": "@ninguem"}, follow_redirects=True)
    assert "Não encontramos ninguém com o usuário @ninguem" in r.get_data(as_text=True)
    r = cliente.post("/amigos/adicionar", data={"usuario": "davi.r"}, follow_redirects=True)
    assert "seu próprio usuário" in r.get_data(as_text=True)
    # busca por parte do usuário ou do nome
    html = cliente.get("/amigos?busca=@dem").get_data(as_text=True)
    assert "@demo" in html and "Adicionar" in html
    assert "@ana.souza" in cliente.get("/amigos?busca=souza").get_data(as_text=True)
    r = cliente.post("/amigos/adicionar", data={"usuario": "@demo", "busca": "dem"}, follow_redirects=True)
    assert "Pedido enviado" in r.get_data(as_text=True) and "Pedido enviado</span>" in r.get_data(as_text=True)
    cliente.get("/sair")
    entrar(cliente)
    html = cliente.get("/amigos").get_data(as_text=True)
    assert "Davi Rocha" in html and "@davi.r" in html
    for pid in re.findall(r'/amigos/pedido/(\d+)/aceitar', html):
        cliente.post(f"/amigos/pedido/{pid}/aceitar")
    html = cliente.get("/amigos").get_data(as_text=True)
    assert "Davi Rocha" in html.split("Seus amigos")[1] and "Pedidos para você" not in html


def test_audio_dublado_legendado_e_idioma(cliente):
    entrar(cliente)
    html = cliente.get("/historico").get_data(as_text=True)
    tid = re.search(r'<option value="(\d+)"[^>]*>Ted Lasso</option>', html).group(1)
    pagina = cliente.get(f"/titulo/{tid}").get_data(as_text=True)
    assert "Áudio original: Inglês" in pagina and "1 pessoa assistiu dublado" in pagina      # a Ana assistiu dublado
    assert "Áudio e legenda não informados pela plataforma" in pagina                        # catálogo de demonstração
    cliente.post("/historico", data={"titulo_id": tid, "plataforma_id": "6", "minutos": "35", "audio": "legendado"})
    pagina = cliente.get(f"/titulo/{tid}").get_data(as_text=True)
    assert "1 pessoa assistiu legendado" in pagina
    r = cliente.post("/historico", data={"titulo_id": tid, "plataforma_id": "6", "minutos": "35", "audio": "xyz"}, follow_redirects=True)
    assert "Escolha como você assistiu" in r.get_data(as_text=True)
    # filtro de idioma: só títulos nacionais
    html = cliente.get("/recomendar?tempo=livre&companhia=sozinho&classificacao=18&idioma=pt").get_data(as_text=True)
    assert "Central do Brasil" in html and "Stranger Things" not in html and "Nacional</span>" in html
    assert "Round 6" in cliente.get("/recomendar?tempo=livre&companhia=sozinho&classificacao=18&idioma=ko").get_data(as_text=True)


def test_catalogo_salva_chave_conferida(cliente, monkeypatch):
    import app as aplicacao
    entrar(cliente)
    monkeypatch.setattr(aplicacao.ClienteTMDB, "testar", lambda self: (_ for _ in ()).throw(aplicacao.ErroTMDB("Chave do TMDB inválida.")))
    r = cliente.post("/catalogo", data={"acao": "salvar", "chave": "errada"}, follow_redirects=True)
    assert "Chave do TMDB inválida" in r.get_data(as_text=True)
    monkeypatch.setattr(aplicacao.ClienteTMDB, "testar", lambda self: True)
    r = cliente.post("/catalogo", data={"acao": "salvar", "chave": "certa"}, follow_redirects=True)
    assert "Chave conferida e salva" in r.get_data(as_text=True) and "Chave configurada" in r.get_data(as_text=True)


def test_registrar_historico_e_validacao(cliente):
    entrar(cliente)
    # Bluey (Disney+ = id 3)
    tid = re.search(r'<option value="(\d+)"[^>]*>Bluey</option>', cliente.get("/historico").get_data(as_text=True)).group(1)
    cliente.post("/historico", data={"titulo_id": tid, "plataforma_id": "3", "minutos": "16"})
    assert "Bluey" in cliente.get("/historico").get_data(as_text=True).split("Registros")[1]
    # plataforma errada
    r = cliente.post("/historico", data={"titulo_id": tid, "plataforma_id": "1", "minutos": "16"}, follow_redirects=True)
    assert "não está nessa plataforma" in r.get_data(as_text=True)


def test_relatorio_do_demo(cliente):
    entrar(cliente)
    html = cliente.get("/relatorio").get_data(as_text=True)
    assert "Sugerimos pausar" in html and "HBO Max" in html
    assert "R$ 358,80" in html


def test_fluxo_de_recuperacao_de_senha(cliente):
    html = cliente.post("/recuperar", data={"email": "demo@streamsmart.com"}).get_data(as_text=True)
    link = re.search(r'href="http://localhost(/redefinir/[^"]+)"', html).group(1)
    r = cliente.post(link, data={"senha": "novasenha", "confirmar": "novasenha"})
    assert r.status_code == 302
    assert entrar(cliente, senha="demo123").status_code == 401
    assert entrar(cliente, senha="novasenha").status_code == 302
    # o link não pode ser usado de novo
    assert cliente.get(link).status_code == 302
