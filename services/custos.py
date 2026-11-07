"""
Regras de custos e cobranças (RF03 e RF04).

As funções recebem as assinaturas como dicionários com as chaves:
id, plataforma, cor, plano, valor, periodicidade ('mensal' ou 'anual'),
dia_vencimento, mes_vencimento (só anual) e fim_teste (AAAA-MM-DD ou None).
"""
import calendar
from datetime import date

from .estruturas import MinHeap

DIAS_ALERTA = 5  # RF03: destacar vencimentos nos próximos 5 dias


def valor_mensal(assinatura):
    """Converte o valor para custo mensal equivalente (plano anual / 12)."""
    if assinatura["periodicidade"] == "anual":
        return round(assinatura["valor"] / 12, 2)
    return round(assinatura["valor"], 2)


def _data_segura(ano, mes, dia):
    """Cria a data ajustando o dia ao último dia do mês (ex.: dia 31 em fevereiro vira 28/29)."""
    ultimo = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(dia, ultimo))


def proximo_vencimento(assinatura, hoje):
    """Calcula a data da próxima cobrança a partir de hoje (inclusive)."""
    dia = assinatura["dia_vencimento"]
    if assinatura["periodicidade"] == "anual":
        mes = assinatura.get("mes_vencimento") or hoje.month
        data = _data_segura(hoje.year, mes, dia)
        return data if data >= hoje else _data_segura(hoje.year + 1, mes, dia)

    data = _data_segura(hoje.year, hoje.month, dia)
    if data >= hoje:
        return data
    ano, mes = (hoje.year + 1, 1) if hoje.month == 12 else (hoje.year, hoje.month + 1)
    return _data_segura(ano, mes, dia)


def resumo(assinaturas):
    """RF04: soma mensal, projeção anual e assinatura mais cara."""
    total_mensal = round(sum(valor_mensal(a) for a in assinaturas), 2)
    mais_cara = None
    for a in assinaturas:
        if mais_cara is None or valor_mensal(a) > valor_mensal(mais_cara):
            mais_cara = a
    return {
        "total_mensal": total_mensal,
        "projecao_anual": round(total_mensal * 12, 2),
        "quantidade": len(assinaturas),
        "mais_cara": mais_cara,
    }


def alertas(assinaturas, hoje, limite=DIAS_ALERTA):
    """RF03: lista os alertas dos próximos `limite` dias, do mais urgente ao menos urgente.

    Cada evento (cobrança ou fim de teste grátis) é inserido numa fila de
    prioridade (MinHeap) com a chave (dias_restantes, ordem). Depois os eventos
    são retirados do heap, sempre o mais próximo primeiro, até passar do limite.
    """
    heap = MinHeap()
    ordem = 0  # desempate estável e evita comparar dicionários
    for a in assinaturas:
        if a.get("fim_teste"):
            fim = date.fromisoformat(a["fim_teste"])
            dias = (fim - hoje).days
            if dias >= 0:
                heap.inserir((dias, ordem, "teste", a))
                ordem += 1
        if a["valor"] > 0:
            dias = (proximo_vencimento(a, hoje) - hoje).days
            heap.inserir((dias, ordem, "cobranca", a))
            ordem += 1

    resultado = []
    while not heap.vazio() and heap.topo()[0] <= limite:
        dias, _, tipo, a = heap.remover()
        if tipo == "teste":
            texto = "Teste grátis expira hoje!" if dias == 0 else f"Teste grátis expira em {dias} dia{'s' if dias > 1 else ''}"
        else:
            texto = "Renovação hoje!" if dias == 0 else f"Renovação em {dias} dia{'s' if dias > 1 else ''}!"
        resultado.append({"assinatura": a, "dias": dias, "tipo": tipo, "texto": texto})
    return resultado


def cobrancas_do_mes(assinaturas, hoje):
    """Linha do tempo: cobranças que caem no mês corrente, ordenadas por dia."""
    eventos = []
    for a in assinaturas:
        if a["valor"] <= 0:
            continue
        if a["periodicidade"] == "anual" and (a.get("mes_vencimento") or hoje.month) != hoje.month:
            continue
        data = _data_segura(hoje.year, hoje.month, a["dia_vencimento"])
        eventos.append({"data": data, "dia": data.day, "assinatura": a,
                        "valor": a["valor"], "passou": data < hoje})
    eventos.sort(key=lambda e: e["dia"])
    return eventos


def fatias_pizza(assinaturas):
    """Distribuição percentual do gasto mensal por plataforma (para o gráfico de pizza)."""
    total = sum(valor_mensal(a) for a in assinaturas)
    if total <= 0:
        return []
    fatias = [{"nome": a["plataforma"], "cor": a["cor"], "valor": valor_mensal(a),
               "pct": valor_mensal(a) / total * 100} for a in assinaturas if valor_mensal(a) > 0]
    fatias.sort(key=lambda f: f["valor"], reverse=True)
    return fatias
