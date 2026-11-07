"""Testes unitários das estruturas de dados e regras de negócio."""
import random
from datetime import date

import pytest

from services import categorias, custos, recomendador, relatorio
from services.estruturas import MinHeap, busca_binaria, insertion_sort, merge_sort


# ------------------------------------------------------------ estruturas
def test_minheap_remove_sempre_o_menor():
    numeros = random.Random(42).sample(range(1000), 200)
    heap = MinHeap()
    for n in numeros:
        heap.inserir(n)
    saida = [heap.remover() for _ in range(len(numeros))]
    assert saida == sorted(numeros)
    assert heap.vazio()


def test_minheap_vazio_gera_erro():
    with pytest.raises(IndexError):
        MinHeap().remover()


@pytest.mark.parametrize("ordenar", [merge_sort, insertion_sort])
def test_ordenacoes_iguais_ao_sorted(ordenar):
    rnd = random.Random(7)
    for tamanho in (0, 1, 2, 10, 101):
        dados = [rnd.randint(-50, 50) for _ in range(tamanho)]
        assert ordenar(dados) == sorted(dados)


def test_merge_sort_estavel_e_nao_altera_original():
    dados = [("b", 1), ("a", 2), ("c", 1), ("d", 2)]
    copia = list(dados)
    resultado = merge_sort(dados, chave=lambda x: x[1])
    assert resultado == [("b", 1), ("c", 1), ("a", 2), ("d", 2)]
    assert dados == copia


def test_busca_binaria():
    lista = list(range(0, 100, 3))
    assert busca_binaria(lista, 27) == 9
    assert busca_binaria(lista, 28) == -1
    assert busca_binaria([], 1) == -1


# ------------------------------------------------------------ custos
def assinatura(**kw):
    base = {"id": 1, "plataforma": "Netflix", "cor": "#000", "plano": "Padrão", "valor": 40.0,
            "periodicidade": "mensal", "dia_vencimento": 10, "mes_vencimento": None, "fim_teste": None}
    base.update(kw)
    return base


def test_valor_mensal_de_plano_anual():
    assert custos.valor_mensal(assinatura(valor=120.0, periodicidade="anual", mes_vencimento=3)) == 10.0


def test_proximo_vencimento_mesmo_mes_e_mes_seguinte():
    a = assinatura(dia_vencimento=10)
    assert custos.proximo_vencimento(a, date(2026, 11, 7)) == date(2026, 11, 10)
    assert custos.proximo_vencimento(a, date(2026, 11, 10)) == date(2026, 11, 10)
    assert custos.proximo_vencimento(a, date(2026, 11, 11)) == date(2026, 12, 10)


def test_proximo_vencimento_virada_de_ano_e_dia_31():
    assert custos.proximo_vencimento(assinatura(dia_vencimento=5), date(2026, 12, 20)) == date(2027, 1, 5)
    # dia 31 em fevereiro vira o último dia do mês
    assert custos.proximo_vencimento(assinatura(dia_vencimento=31), date(2027, 2, 1)) == date(2027, 2, 28)


def test_proximo_vencimento_anual():
    a = assinatura(periodicidade="anual", dia_vencimento=15, mes_vencimento=3)
    assert custos.proximo_vencimento(a, date(2026, 11, 7)) == date(2027, 3, 15)


def test_resumo_soma_e_projecao():
    lista = [assinatura(valor=44.90), assinatura(id=2, plataforma="Max", valor=29.90),
             assinatura(id=3, plataforma="Prime", valor=166.80, periodicidade="anual", mes_vencimento=1)]
    r = custos.resumo(lista)
    assert r["total_mensal"] == 88.70
    assert r["projecao_anual"] == 1064.40
    assert r["mais_cara"]["plataforma"] == "Netflix"


def test_alertas_ordenados_por_urgencia_e_limitados_a_5_dias():
    hoje = date(2026, 11, 7)
    lista = [assinatura(id=1, plataforma="A", dia_vencimento=11),   # 4 dias
             assinatura(id=2, plataforma="B", dia_vencimento=8),    # 1 dia
             assinatura(id=3, plataforma="C", dia_vencimento=20),   # 13 dias (fora)
             assinatura(id=4, plataforma="D", valor=0, dia_vencimento=25, fim_teste="2026-11-09")]
    al = custos.alertas(lista, hoje)
    assert [(a["assinatura"]["plataforma"], a["dias"], a["tipo"]) for a in al] == [
        ("B", 1, "cobranca"), ("D", 2, "teste"), ("A", 4, "cobranca")]
    assert al[0]["texto"] == "Renovação em 1 dia!"


# ------------------------------------------------------------ recomendador
def titulo(**kw):
    base = {"id": 1, "titulo": "X", "tipo": "filme", "ano": 2020, "duracao_min": 90, "generos": ["comédia"],
            "vibes": ["rir"], "classificacao": "12", "sinopse": "", "nota_tmdb": 7.0,
            "plataformas": [{"id": 1, "nome": "Netflix", "cor": "#f00"}]}
    base.update(kw)
    return base


FILTROS = {"tempo": "90", "vibes": ["rir"], "companhia": "sozinho", "classificacao_max": "18", "somente_minhas": False}


def test_descarta_filme_mais_longo_que_o_tempo():
    assert recomendador.pontuar(titulo(duracao_min=120), FILTROS, {"Netflix"}) is None
    assert recomendador.pontuar(titulo(duracao_min=90), FILTROS, {"Netflix"}) is not None
    assert recomendador.pontuar(titulo(duracao_min=400), {**FILTROS, "tempo": "livre"}, set()) is not None


def test_serie_conta_episodios_que_cabem():
    t = titulo(tipo="serie", duracao_min=22)
    _, motivos = recomendador.pontuar(t, {**FILTROS, "tempo": "30"}, {"Netflix"})
    assert "1 episódio cabe no seu tempo" in motivos


def test_descarta_vibe_diferente_e_aceita_qualquer_das_vibes():
    terror = titulo(generos=["terror"], vibes=[])
    assert recomendador.pontuar(terror, FILTROS, set()) is None
    assert recomendador.pontuar(terror, {**FILTROS, "vibes": ["rir", "medo"]}, set()) is not None


def test_nostalgia_usa_o_ano():
    assert categorias.afinidade(titulo(ano=1995, vibes=[]), "nostalgia") == 1.0
    assert categorias.afinidade(titulo(ano=2022, vibes=[]), "nostalgia") == 0.0


def test_filtros_de_categoria_e_formato():
    f = {**FILTROS, "vibes": [], "categorias": ["drama", "romance"]}
    assert recomendador.pontuar(titulo(generos=["comédia"]), f, set()) is None
    assert recomendador.pontuar(titulo(generos=["comédia", "romance"]), f, set()) is not None
    assert recomendador.pontuar(titulo(), {**FILTROS, "tipo": "serie"}, set()) is None


def test_classificacao_maxima_e_sem_informacao():
    assert recomendador.pontuar(titulo(classificacao="16"), {**FILTROS, "classificacao_max": "14"}, set()) is None
    assert recomendador.pontuar(titulo(classificacao="14"), {**FILTROS, "classificacao_max": "14"}, set()) is not None
    # sem classificação: só aparece a partir de 14 anos e nunca com crianças
    assert recomendador.pontuar(titulo(classificacao=None), {**FILTROS, "classificacao_max": "12"}, set()) is None
    assert recomendador.pontuar(titulo(classificacao=None), {**FILTROS, "classificacao_max": "16"}, set()) is not None


def test_criancas_exige_classificacao_livre_ou_10():
    f = {**FILTROS, "companhia": "criancas"}
    assert recomendador.pontuar(titulo(classificacao="12"), f, set()) is None
    assert recomendador.pontuar(titulo(classificacao="L"), f, set()) is not None


def test_filtro_de_plataformas_e_somente_minhas():
    assert recomendador.pontuar(titulo(), {**FILTROS, "plataformas": ["Disney+"]}, set()) is None
    assert recomendador.pontuar(titulo(), {**FILTROS, "plataformas": ["Netflix"]}, set()) is not None
    f = {**FILTROS, "somente_minhas": True}
    assert recomendador.pontuar(titulo(), f, {"Disney+"}) is None
    assert recomendador.pontuar(titulo(), f, {"Netflix"}) is not None


def test_titulo_no_plano_vem_antes_e_lista_vem_inteira():
    catalogo = [titulo(id=1, titulo="Fora", plataformas=[{"id": 2, "nome": "HBO Max", "cor": "#00f"}]),
                titulo(id=2, titulo="Dentro")] + [titulo(id=10 + i, titulo=f"T{i:02d}") for i in range(40)]
    resultado = recomendador.recomendar(catalogo, FILTROS, {"Netflix"})
    assert len(resultado) == 42                     # sem limite de quantidade
    assert resultado[-1]["titulo"] == "Fora" and not resultado[-1]["no_plano"]


def test_ordenacoes():
    catalogo = [titulo(id=1, titulo="Velho", ano=1990, duracao_min=80, nota_tmdb=9.0),
                titulo(id=2, titulo="Novo", ano=2024, duracao_min=60, nota_tmdb=6.0)]
    ordem = lambda o: [r["titulo"] for r in recomendador.recomendar(catalogo, {**FILTROS, "ordenar": o}, set())]
    assert ordem("recentes") == ["Novo", "Velho"]
    assert ordem("avaliacao") == ["Velho", "Novo"]
    assert ordem("curtos") == ["Novo", "Velho"]


def test_amigos_aumentam_a_nota_e_ja_assistido_diminui():
    t = titulo()
    base, _ = recomendador.pontuar(t, FILTROS, {"Netflix"})
    com_amigos, motivos = recomendador.pontuar(t, FILTROS, {"Netflix"}, notas_amigos={1: (4.5, 2)})
    assert com_amigos > base and any("amigos" in m for m in motivos)
    vista, motivos = recomendador.pontuar(t, FILTROS, {"Netflix"}, ja_assistidos={1})
    assert vista < base and "Você já assistiu" in motivos


def test_filtro_de_idioma_original():
    f = {**FILTROS, "vibes": []}
    assert recomendador.pontuar(titulo(idioma_original="ko"), {**f, "idiomas": ["ko"]}, set()) is not None
    assert recomendador.pontuar(titulo(idioma_original="en"), {**f, "idiomas": ["ko", "ja"]}, set()) is None
    assert recomendador.pontuar(titulo(idioma_original="tr"), {**f, "idiomas": ["outros"]}, set()) is not None
    assert recomendador.pontuar(titulo(idioma_original="en"), {**f, "idiomas": ["outros"]}, set()) is None


def test_normalizacoes_de_categoria_e_classificacao():
    assert categorias.normalizar_generos(["policial", "Comédia", "comédia", "xyz"]) == ["crime", "comédia"]
    assert categorias.normalizar_classificacao("L") == "L"
    assert categorias.normalizar_classificacao("Livre") == "L"
    assert categorias.normalizar_classificacao("14") == "14"
    assert categorias.normalizar_classificacao("") is None


# ------------------------------------------------------------ relatório
def test_relatorio_classifica_assinaturas():
    hoje = date(2026, 11, 7)
    assinaturas = [assinatura(id=1, plataforma="Netflix", valor=44.90),
                   assinatura(id=2, plataforma="HBO Max", valor=29.90),
                   assinatura(id=3, plataforma="Disney+", valor=46.90)]
    historico = [
        {"plataforma": "Netflix", "titulo_id": 1, "data": "2026-11-01", "minutos": 600},
        {"plataforma": "Netflix", "titulo_id": 2, "data": "2026-11-03", "minutos": 400},
        {"plataforma": "HBO Max", "titulo_id": 3, "data": "2026-08-20", "minutos": 120},  # fora da janela
        {"plataforma": "Disney+", "titulo_id": 4, "data": "2026-11-05", "minutos": 100},
    ]
    r = relatorio.analisar(assinaturas, historico, hoje)
    por_nome = {l["assinatura"]["plataforma"]: l for l in r["linhas"]}
    assert por_nome["HBO Max"]["status"] == "pausar"
    assert "2 meses" in por_nome["HBO Max"]["sugestao"]
    assert por_nome["Disney+"]["status"] == "avaliar"
    assert por_nome["Netflix"]["status"] == "manter"
    assert por_nome["Netflix"]["custo_hora"] == round(44.90 / (1000 / 60), 2)
    assert r["economia_mensal"] == 29.90
    assert r["linhas"][0]["status"] == "pausar"   # piores primeiro


def test_mais_assistida():
    hist = [{"plataforma": "A", "titulo_id": 1, "data": "2026-11-01", "minutos": 60},
            {"plataforma": "B", "titulo_id": 2, "data": "2026-11-02", "minutos": 90}]
    assert relatorio.mais_assistida(hist, date(2026, 11, 7)) == {"plataforma": "B", "horas": 1.5}
    assert relatorio.mais_assistida([], date(2026, 11, 7)) is None
