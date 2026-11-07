"""
Recomendador "O que assistir hoje?" (RF05 e RF06).

Funciona em duas etapas:
1. Filtragem: elimina títulos incompatíveis (não cabem no tempo, não têm a
   vibe pedida, classificação imprópria para crianças ou, se o usuário pediu,
   fora das plataformas que ele assina).
2. Pontuação e ordenação: cada título restante recebe uma nota de 0 a 100 e
   a lista é ordenada com merge sort (nota decrescente, título em ordem alfabética
   no empate).
"""
from .estruturas import merge_sort

TEMPOS = {
    "30": {"rotulo": "Tenho 30 min", "minutos": 30},
    "90": {"rotulo": "Tenho 1h30", "minutos": 90},
    "noite": {"rotulo": "Tenho a noite toda", "minutos": None},
}
VIBES = {
    "rir": "Quero rir",
    "suspense": "Suspense tenso",
    "emocao": "Chorar de emoção",
    "leve": "Filme leve de fundo",
}
COMPANHIAS = {
    "sozinho": "Sozinho",
    "casal": "Em casal",
    "criancas": "Com crianças",
}
CLASSIFICACAO_INFANTIL = {"L", "10"}

# Pesos da pontuação (somam 100)
PESO_VIBE = 35
PESO_TEMPO = 25
PESO_PLATAFORMA = 25
PESO_COMPANHIA = 15
PENALIDADE_JA_ASSISTIU = 20


def episodios_que_cabem(titulo, minutos):
    if titulo["tipo"] != "serie" or minutos is None:
        return None
    return max(minutos // titulo["duracao_min"], 0)


def pontuar(titulo, filtros, plataformas_usuario, ja_assistidos=frozenset()):
    """Retorna (nota, motivos) ou None quando o título deve ser descartado.

    filtros: dict com 'tempo', 'vibe', 'companhia' e 'somente_minhas' (bool).
    plataformas_usuario: conjunto (set) com os nomes das plataformas assinadas.
    """
    motivos = []
    nota = 0.0

    # --- Vibe (obrigatória) ---
    vibe = filtros.get("vibe")
    if vibe:
        if vibe not in titulo["vibes"]:
            return None
        # a vibe principal do título é a primeira da lista
        nota += PESO_VIBE if titulo["vibes"][0] == vibe else PESO_VIBE * 0.6
    else:
        nota += PESO_VIBE * 0.5

    # --- Tempo disponível (obrigatório) ---
    limite = TEMPOS.get(filtros.get("tempo"), TEMPOS["noite"])["minutos"]
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
            motivos.append("Cabe no seu tempo")
        nota += PESO_TEMPO * aproveitamento
    else:
        # noite livre: filmes longos e séries para maratonar são valorizados
        if titulo["tipo"] == "filme":
            nota += PESO_TEMPO * min(duracao / 140, 1)
        else:
            nota += PESO_TEMPO * 0.8
            motivos.append("Boa para maratonar")

    # --- Companhia ---
    companhia = filtros.get("companhia", "sozinho")
    generos = titulo["generos"]
    if companhia == "criancas":
        if titulo["classificacao"] not in CLASSIFICACAO_INFANTIL:
            return None
        nota += PESO_COMPANHIA if ("família" in generos or "infantil" in generos or "animação" in generos) else PESO_COMPANHIA * 0.4
        motivos.append(f"Classificação {titulo['classificacao']}")
    elif companhia == "casal":
        nota += PESO_COMPANHIA if ("romance" in generos or "comédia" in generos) else PESO_COMPANHIA * 0.5
    else:
        nota += PESO_COMPANHIA * 0.7

    # --- Plataforma (RF06) ---
    nomes = {p["nome"] for p in titulo["plataformas"]}
    disponiveis = nomes & plataformas_usuario  # interseção de conjuntos
    if filtros.get("somente_minhas") and not disponiveis:
        return None
    if disponiveis:
        nota += PESO_PLATAFORMA
        motivos.insert(0, "Disponível no seu plano")

    # --- Já assistido ---
    if titulo["id"] in ja_assistidos:
        nota -= PENALIDADE_JA_ASSISTIU
        motivos.append("Você já assistiu")

    return round(max(nota, 0), 1), motivos


def recomendar(catalogo, filtros, plataformas_usuario, ja_assistidos=frozenset(), limite=12):
    """Aplica filtros, pontua e devolve os `limite` melhores títulos."""
    candidatos = []
    for titulo in catalogo:
        r = pontuar(titulo, filtros, plataformas_usuario, ja_assistidos)
        if r is None:
            continue
        nota, motivos = r
        nomes = [p["nome"] for p in titulo["plataformas"]]
        candidatos.append({
            **titulo,
            "nota": nota,
            "motivos": motivos,
            "no_plano": bool(set(nomes) & plataformas_usuario),
        })
    ordenados = merge_sort(candidatos, chave=lambda c: (-c["nota"], c["titulo"]))
    return ordenados[:limite], len(candidatos)
