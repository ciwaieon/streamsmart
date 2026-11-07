"""
Vocabulário do catálogo: categorias (gêneros), vibes, tempos e classificação indicativa.

Tanto o catálogo de demonstração quanto o importado do TMDB são convertidos para
estas mesmas categorias, para que os filtros funcionem igual nas duas origens.
"""

# Categorias exibidas no filtro (ordem alfabética de exibição)
CATEGORIAS = [
    "ação", "animação", "aventura", "comédia", "crime", "documentário", "drama", "família",
    "fantasia", "faroeste", "ficção científica", "guerra", "história", "infantil", "mistério",
    "musical", "reality", "romance", "suspense", "terror",
]

# Sinônimos usados no catálogo de demonstração -> categoria padronizada
SINONIMOS = {
    "policial": "crime", "super-herói": "ação", "esporte": "drama", "novela": "drama",
    "médico": "drama", "biografia": "história", "histórico": "história", "natureza": "documentário",
    "culinária": "reality",
}

# Gêneros do TMDB (ids oficiais, iguais em qualquer idioma) -> categorias
TMDB_GENEROS = {
    28: ["ação"], 12: ["aventura"], 16: ["animação"], 35: ["comédia"], 80: ["crime"],
    99: ["documentário"], 18: ["drama"], 10751: ["família"], 14: ["fantasia"], 36: ["história"],
    27: ["terror"], 10402: ["musical"], 9648: ["mistério"], 10749: ["romance"],
    878: ["ficção científica"], 53: ["suspense"], 10752: ["guerra"], 37: ["faroeste"],
    10770: ["drama"],
    # séries
    10759: ["ação", "aventura"], 10762: ["infantil"], 10764: ["reality"], 10765: ["ficção científica", "fantasia"],
    10766: ["drama"], 10767: ["reality"], 10768: ["guerra", "história"], 10763: ["documentário"],
}


def normalizar_generos(generos):
    """Converte uma lista de gêneros para as categorias padronizadas, sem repetir."""
    resultado = []
    for g in generos:
        g = SINONIMOS.get(g.strip().lower(), g.strip().lower())
        if g in CATEGORIAS and g not in resultado:
            resultado.append(g)
    return resultado


# ------------------------------------------------------------------ vibes
# Cada vibe tem um rótulo, uma descrição curta e as categorias que combinam com ela (com peso).
VIBES = {
    "rir": {"rotulo": "Quero rir", "descricao": "Comédia para dar risada de verdade",
            "categorias": {"comédia": 1.0, "animação": 0.6, "família": 0.5}},
    "relaxar": {"rotulo": "Desligar a cabeça", "descricao": "Algo leve, sem esforço",
                "categorias": {"comédia": 0.9, "família": 0.9, "animação": 0.8, "romance": 0.7, "reality": 0.8, "musical": 0.7}},
    "tensao": {"rotulo": "Roer as unhas", "descricao": "Suspense, crime e mistério",
               "categorias": {"suspense": 1.0, "mistério": 1.0, "crime": 0.9}},
    "adrenalina": {"rotulo": "Adrenalina", "descricao": "Ação, perseguição e explosão",
                   "categorias": {"ação": 1.0, "aventura": 0.8, "guerra": 0.8, "faroeste": 0.6}},
    "medo": {"rotulo": "Levar um susto", "descricao": "Terror para ver com a luz apagada",
             "categorias": {"terror": 1.0, "suspense": 0.5}},
    "emocao": {"rotulo": "Chorar um pouco", "descricao": "Histórias que mexem com a gente",
               "categorias": {"drama": 1.0, "romance": 0.7, "família": 0.4}},
    "romance": {"rotulo": "Clima de romance", "descricao": "Para ver junto, de preferência",
                "categorias": {"romance": 1.0, "comédia": 0.4, "musical": 0.4}},
    "pensar": {"rotulo": "Algo para pensar", "descricao": "Para sair com a cabeça fervendo",
               "categorias": {"documentário": 1.0, "ficção científica": 0.9, "história": 0.9, "drama": 0.6, "mistério": 0.5}},
    "viajar": {"rotulo": "Ir para outro mundo", "descricao": "Fantasia, aventura e ficção",
               "categorias": {"fantasia": 1.0, "ficção científica": 1.0, "aventura": 0.9, "animação": 0.6}},
    "inspirar": {"rotulo": "Sair inspirado", "descricao": "Histórias reais e de superação",
                 "categorias": {"história": 1.0, "documentário": 0.9, "musical": 0.6, "drama": 0.5}},
    "nostalgia": {"rotulo": "Bater a nostalgia", "descricao": "Clássicos de antes de 2010",
                  "categorias": {}},  # calculada pelo ano de lançamento
    "fundo": {"rotulo": "Deixar de fundo", "descricao": "Para ver enquanto faz outra coisa",
              "categorias": {"reality": 1.0, "documentário": 0.7, "comédia": 0.6}},
}

# Vibes antigas do catálogo de demonstração -> vibes novas (dão um bônus de precisão)
VIBES_ANTIGAS = {"rir": "rir", "suspense": "tensao", "emocao": "emocao", "leve": "relaxar"}


def afinidade(titulo, vibe):
    """Quanto um título combina com uma vibe, de 0 (nada) a 1 (totalmente)."""
    if vibe == "nostalgia":
        ano = titulo.get("ano") or 2100
        return 1.0 if ano < 2000 else 0.85 if ano < 2010 else 0.0
    pesos = VIBES[vibe]["categorias"]
    generos = titulo["generos"]
    melhor = 0.0
    for i, g in enumerate(generos):
        if g in pesos:
            # o primeiro gênero é o principal; os demais valem um pouco menos
            melhor = max(melhor, pesos[g] * (1.0 if i == 0 else 0.85))
    if vibe in titulo.get("vibes", []):
        melhor = max(melhor, 1.0 if titulo["vibes"][0] == vibe else 0.8)
    if vibe == "fundo" and titulo["tipo"] == "serie" and titulo["duracao_min"] <= 30:
        melhor = max(melhor, 0.7)  # séries curtas funcionam bem de fundo
    return melhor


# ------------------------------------------------------------------ tempo
TEMPOS = [
    ("20", "20 min", 20), ("30", "30 min", 30), ("45", "45 min", 45), ("60", "1 hora", 60),
    ("90", "1h30", 90), ("120", "2 horas", 120), ("150", "2h30", 150), ("180", "3 horas", 180),
    ("livre", "A noite toda", None),
]
TEMPOS_MIN = {chave: minutos for chave, _, minutos in TEMPOS}

# ------------------------------------------------------------------ classificação indicativa
CLASSIFICACOES = ["L", "10", "12", "14", "16", "18"]
DESCRICAO_CLASSIFICACAO = {"L": "Livre", "10": "10 anos", "12": "12 anos", "14": "14 anos",
                           "16": "16 anos", "18": "18 anos"}


def nivel_classificacao(c):
    """Posição da classificação na escala (0 = Livre ... 5 = 18). None = sem informação."""
    return CLASSIFICACOES.index(c) if c in CLASSIFICACOES else None


def normalizar_classificacao(texto):
    """Converte o texto vindo do TMDB ('L', 'Livre', '12', 'A12'...) para a escala padrão."""
    if not texto:
        return None
    t = texto.strip().upper().replace("ANOS", "").replace("A", "").strip()
    if texto.strip().upper() in ("L", "LIVRE", "AL", "ER"):
        return "L"
    return t if t in CLASSIFICACOES else None
