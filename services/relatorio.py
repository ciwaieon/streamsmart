"""
Relatório de custo-benefício (RF08).

Cruza o histórico do usuário (RF07) com o valor pago em cada assinatura e
sugere manter, avaliar ou pausar cada uma.
"""
from datetime import date, timedelta

from .custos import valor_mensal
from .estruturas import merge_sort

JANELA_DIAS = 30            # período analisado
CUSTO_HORA_ALTO = 15.00     # acima disso (R$/hora) a assinatura merece reavaliação
MINIMO_TITULOS = 2          # menos que isso no período = uso baixo


def brl(valor):
    """Formata valores no padrão brasileiro (R$ 1.234,56)."""
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def analisar(assinaturas, historico, hoje=None):
    """assinaturas: lista de dicts (ver custos.py).
    historico: lista de dicts com 'plataforma', 'titulo_id', 'data' (AAAA-MM-DD) e 'minutos'.
    """
    hoje = hoje or date.today()
    inicio = hoje - timedelta(days=JANELA_DIAS)

    # Agrupa o histórico por plataforma usando um dicionário (tabela hash)
    uso = {}
    for h in historico:
        d = date.fromisoformat(h["data"])
        info = uso.setdefault(h["plataforma"], {"minutos": 0, "titulos": set(), "ultimo": None})
        if info["ultimo"] is None or d > info["ultimo"]:
            info["ultimo"] = d
        if inicio <= d <= hoje:
            info["minutos"] += h["minutos"]
            info["titulos"].add(h["titulo_id"])

    linhas = []
    for a in assinaturas:
        info = uso.get(a["plataforma"], {"minutos": 0, "titulos": set(), "ultimo": None})
        custo = valor_mensal(a)
        horas = info["minutos"] / 60
        qtd = len(info["titulos"])
        custo_hora = round(custo / horas, 2) if horas > 0 else None
        dias_sem_uso = (hoje - info["ultimo"]).days if info["ultimo"] else None

        if a.get("fim_teste") and a["valor"] == 0:
            status, cor = "teste", "info"
            fim = date.fromisoformat(a["fim_teste"])
            sugestao = (f"Teste grátis termina em {fim.strftime('%d/%m')}. "
                        + ("Você já está usando: decida se vale assinar." if qtd else
                           "Você ainda não usou: cancele antes da cobrança."))
        elif horas == 0:
            status, cor = "pausar", "ruim"
            if dias_sem_uso is None:
                sugestao = f"Nenhum título registrado nesta plataforma. Que tal pausar e economizar {brl(custo)}/mês?"
            else:
                meses = dias_sem_uso // 30
                tempo = f"{meses} {'mês' if meses == 1 else 'meses'}" if meses >= 1 else f"{dias_sem_uso} dias"
                sugestao = f"Você paga {brl(custo)}/mês, mas não assiste a nada nela há {tempo}. Que tal pausar?"
        elif qtd < MINIMO_TITULOS or (custo_hora is not None and custo_hora > CUSTO_HORA_ALTO):
            status, cor = "avaliar", "medio"
            sugestao = (f"Você assistiu a apenas {qtd} título{'s' if qtd != 1 else ''} nos últimos {JANELA_DIAS} dias "
                        f"({brl(custo_hora)} por hora). Avalie pausar até ter algo para ver.")
        else:
            status, cor = "manter", "bom"
            sugestao = f"Bom custo-benefício: {brl(custo_hora)} por hora assistida."

        linhas.append({
            "assinatura": a, "custo_mensal": custo, "horas": round(horas, 1), "titulos": qtd,
            "custo_hora": custo_hora, "dias_sem_uso": dias_sem_uso,
            "status": status, "cor": cor, "sugestao": sugestao,
        })

    # Ordena: piores primeiro (pausar, avaliar, teste, manter); dentro do grupo, maior custo/hora primeiro
    prioridade = {"pausar": 0, "avaliar": 1, "teste": 2, "manter": 3}
    linhas = merge_sort(linhas, chave=lambda l: (prioridade[l["status"]],
                                                 -(l["custo_hora"] if l["custo_hora"] is not None else 9999)))
    economia = round(sum(l["custo_mensal"] for l in linhas if l["status"] == "pausar"), 2)
    return {"linhas": linhas, "economia_mensal": economia, "economia_anual": round(economia * 12, 2),
            "janela": JANELA_DIAS}


def mais_assistida(historico, hoje=None):
    """Plataforma com mais minutos assistidos na janela de análise."""
    hoje = hoje or date.today()
    inicio = hoje - timedelta(days=JANELA_DIAS)
    minutos = {}
    for h in historico:
        if inicio <= date.fromisoformat(h["data"]) <= hoje:
            minutos[h["plataforma"]] = minutos.get(h["plataforma"], 0) + h["minutos"]
    if not minutos:
        return None
    nome = max(minutos, key=minutos.get)
    return {"plataforma": nome, "horas": round(minutos[nome] / 60, 1)}
