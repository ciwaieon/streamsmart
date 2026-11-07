"""
Recomendador "O que assistir hoje?" (RF05 e RF06).

Funciona em duas etapas:
1. Filtragem: elimina os títulos incompatíveis com o que o usuário escolheu
   (tempo, vibes, categorias, tipo, classificação indicativa, companhia e plataformas).
2. Pontuação e ordenação: cada título restante recebe uma nota de 0 a 100 e a
   lista é ordenada com merge sort pelo critério escolhido.
"""
from .categorias import TEMPOS_MIN, VIBES, afinidade, nivel_classificacao
from .estruturas import merge_sort

COMPANHIAS = {"sozinho": "Sozinho", "casal": "Em casal", "criancas": "Com crianças"}
TIPOS = {"todos": "Filmes e séries", "filme": "Só filmes", "serie": "Só séries"}
ORDENACOES = {
    "compat": "Mais compatíveis",
    "avaliacao": "Mais bem avaliados",
    "recentes": "Mais recentes",
    "curtos": "Mais curtos",
}

# Pesos da pontuação (somam 100 antes do bônus dos amigos)
PESO_VIBE = 35
PESO_TEMPO = 20
PESO_PLATAFORMA = 20
PESO_COMPANHIA = 10
PESO_QUALIDADE = 15
BONUS_AMIGOS = 10
PENALIDADE_JA_ASSISTIU = 20


def episodios_que_cabem(titulo, minutos):
    if titulo["tipo"] != "serie" or minutos is None:
        return None
    return max(minutos // titulo["duracao_min"], 0)


def pontuar(titulo, filtros, plataformas_usuario, ja_assistidos=frozenset(), notas_amigos=None):
    """Retorna (nota, motivos) ou None quando o título deve ser descartado.

    filtros: dict com tempo, vibes (lista), categorias (lista), tipo, classificacao_max,
             companhia, plataformas (lista de nomes) e somente_minhas (bool).
    plataformas_usuario: conjunto (set) com os nomes das plataformas assinadas.
    notas_amigos: dict titulo_id -> (média, quantidade) das avaliações dos amigos.
    """
    motivos = []
    nota = 0.0

    # --- Tipo ---
    tipo = filtros.get("tipo", "todos")
    if tipo in ("filme", "serie") and titulo["tipo"] != tipo:
        return None

    # --- Categorias (pelo menos uma das escolhidas) ---
    categorias = filtros.get("categorias") or []
    if categorias and not set(categorias) & set(titulo["generos"]):
        return None

    # --- Vibes (o título precisa combinar com pelo menos uma) ---
    vibes = filtros.get("vibes") or []
    if vibes:
        melhor_vibe, melhor = None, 0.0
        for v in vibes:
            a = afinidade(titulo, v)
            if a > melhor:
                melhor_vibe, melhor = v, a
        if melhor == 0:
            return None
        nota += PESO_VIBE * melhor
        if len(vibes) > 1:
            motivos.append(f"Combina com “{VIBES[melhor_vibe]['rotulo']}”")
    else:
        nota += PESO_VIBE * 0.5

    # --- Tempo disponível ---
    limite = TEMPOS_MIN.get(filtros.get("tempo"), None)
    duracao = titulo["duracao_min"]
    if limite is not None:
        if duracao > limite:
            return None
        if titulo["tipo"] == "serie":
            eps = episodios_que_cabem(titulo, limite)
            aproveitamento = eps * duracao / limite
            motivos.append(f"{eps} episódio{'s' if eps > 1 else ''} cabe{'m' if eps > 1 else ''} no seu tempo")
        else:
            aproveitamento = duracao / limite
        nota += PESO_TEMPO * aproveitamento
    else:
        nota += PESO_TEMPO * (min(duracao / 140, 1) if titulo["tipo"] == "filme" else 0.8)

    # --- Classificação indicativa e companhia ---
    nivel = nivel_classificacao(titulo.get("classificacao"))
    maximo = nivel_classificacao(filtros.get("classificacao_max", "18"))
    companhia = filtros.get("companhia", "sozinho")
    if companhia == "criancas":
        maximo = min(maximo, 1)                    # com crianças: no máximo 10 anos
    if nivel is None:
        if maximo < 3 or companhia == "criancas":  # sem classificação: só passa a partir de 14 anos
            return None
    elif nivel > maximo:
        return None

    generos = titulo["generos"]
    if companhia == "criancas":
        nota += PESO_COMPANHIA if {"família", "infantil", "animação"} & set(generos) else PESO_COMPANHIA * 0.4
    elif companhia == "casal":
        nota += PESO_COMPANHIA if {"romance", "comédia"} & set(generos) else PESO_COMPANHIA * 0.5
    else:
        nota += PESO_COMPANHIA * 0.7

    # --- Plataformas (RF06) ---
    nomes = {p["nome"] for p in titulo["plataformas"]}
    escolhidas = set(filtros.get("plataformas") or [])
    if escolhidas and not nomes & escolhidas:
        return None
    disponiveis = nomes & plataformas_usuario      # interseção de conjuntos
    if filtros.get("somente_minhas") and not disponiveis:
        return None
    if disponiveis:
        nota += PESO_PLATAFORMA
        motivos.insert(0, "Disponível no seu plano")

    # --- Qualidade (nota do TMDB) ---
    nota_publico = titulo.get("nota_tmdb")
    nota += PESO_QUALIDADE * ((nota_publico / 10) if nota_publico else 0.6)

    # --- Amigos ---
    if notas_amigos and titulo["id"] in notas_amigos:
        media, qtd = notas_amigos[titulo["id"]]
        if media >= 4:
            nota += BONUS_AMIGOS
            motivos.append(f"{qtd} amigo{'s' if qtd > 1 else ''} {'deram' if qtd > 1 else 'deu'} nota {media:.1f}".replace(".", ","))

    # --- Já assistido ---
    if titulo["id"] in ja_assistidos:
        nota -= PENALIDADE_JA_ASSISTIU
        motivos.append("Você já assistiu")

    return round(min(max(nota, 0), 100), 1), motivos


def _chave(ordenar):
    if ordenar == "avaliacao":
        return lambda c: (-(c.get("nota_tmdb") or 0), -c["nota"], c["titulo"])
    if ordenar == "recentes":
        return lambda c: (-(c.get("ano") or 0), -c["nota"], c["titulo"])
    if ordenar == "curtos":
        return lambda c: (c["duracao_min"], -c["nota"], c["titulo"])
    return lambda c: (-c["nota"], c["titulo"])


def recomendar(catalogo, filtros, plataformas_usuario, ja_assistidos=frozenset(), notas_amigos=None):
    """Aplica filtros, pontua e devolve TODOS os títulos compatíveis, já ordenados."""
    candidatos = []
    for titulo in catalogo:
        r = pontuar(titulo, filtros, plataformas_usuario, ja_assistidos, notas_amigos)
        if r is None:
            continue
        nota, motivos = r
        candidatos.append({
            **titulo,
            "nota": nota,
            "motivos": motivos,
            "no_plano": bool({p["nome"] for p in titulo["plataformas"]} & plataformas_usuario),
        })
    return merge_sort(candidatos, chave=_chave(filtros.get("ordenar", "compat")))
