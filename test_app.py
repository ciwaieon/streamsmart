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
    r = cliente.post("/cadastro", data={"nome": "Ana", "email": "ana@x.com", "senha": "123", "confirmar": "123"})
    assert r.status_code == 400
    r = cliente.post("/cadastro", data={"nome": "Ana", "email": "ana@x.com", "senha": "segredo1", "confirmar": "segredo1"})
    assert r.status_code == 302
    cliente.get("/sair")
    r = cliente.post("/cadastro", data={"nome": "Ana", "email": "ana@x.com", "senha": "segredo1", "confirmar": "segredo1"})
    assert "Já existe" in r.get_data(as_text=True)


def test_painel_mostra_totais_do_demo(cliente):
    entrar(cliente)
    html = cliente.get("/painel").get_data(as_text=True)
    assert "R$ 135,60" in html          # 44,90 + 29,90 + 46,90 + 166,80/12 + 0
    assert "R$ 1.627,20" in html
    assert "Renovação em 2 dias!" in html
    assert "Teste grátis expira em 3 dias" in html


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
    cliente.post("/cadastro", data={"nome": "Bia", "email": "bia@x.com", "senha": "segredo1", "confirmar": "segredo1"})
    r = cliente.get("/assinaturas/1/editar")   # assinatura do usuário demo
    assert r.status_code == 302
    cliente.post("/assinaturas/1/excluir")
    cliente.get("/sair")
    entrar(cliente)
    assert "Netflix" in cliente.get("/assinaturas").get_data(as_text=True)


def test_recomendador_respeita_filtros(cliente):
    entrar(cliente)
    html = cliente.get("/recomendar?tempo=30&vibe=leve&companhia=criancas&somente=1").get_data(as_text=True)
    assert "Bluey" in html
    assert "Stranger Things" not in html
    assert "Fora da sua assinatura" not in html
    def total(url):
        return int(re.search(r"(\d+) títulos? combinam", cliente.get(url).get_data(as_text=True)).group(1))
    com_filtro = total("/recomendar?tempo=noite&vibe=emocao&companhia=sozinho&somente=1")
    sem_filtro = total("/recomendar?tempo=noite&vibe=emocao&companhia=sozinho")
    assert sem_filtro > com_filtro   # sem o filtro entram títulos de plataformas não assinadas


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
    assert "R$ 29,90/mês" in html


def test_fluxo_de_recuperacao_de_senha(cliente):
    html = cliente.post("/recuperar", data={"email": "demo@streamsmart.com"}).get_data(as_text=True)
    link = re.search(r'href="http://localhost(/redefinir/[^"]+)"', html).group(1)
    r = cliente.post(link, data={"senha": "novasenha", "confirmar": "novasenha"})
    assert r.status_code == 302
    assert entrar(cliente, senha="demo123").status_code == 401
    assert entrar(cliente, senha="novasenha").status_code == 302
    # o link não pode ser usado de novo
    assert cliente.get(link).status_code == 302
