"""
Benchmark dos algoritmos de ordenação usados no recomendador.

Compara o merge sort e o insertion sort implementados no projeto com o
sorted() nativo do Python (Timsort), ordenando listas de recomendações
fictícias pela mesma chave usada no sistema: (-nota, título).

Uso:  python benchmark.py
Gera: resultados/benchmark.csv e resultados/benchmark.png (se o matplotlib estiver instalado)
"""
import csv
import os
import random
import string
import time

from services.estruturas import insertion_sort, merge_sort

TAMANHOS = [100, 500, 1000, 2000, 5000]
REPETICOES = 5
PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultados")


def gerar_itens(n, rnd):
    return [{"titulo": "".join(rnd.choices(string.ascii_letters, k=8)), "nota": round(rnd.uniform(0, 100), 1)}
            for _ in range(n)]


def chave(item):
    return (-item["nota"], item["titulo"])


def medir(funcao, dados):
    melhor = float("inf")
    for _ in range(REPETICOES):
        inicio = time.perf_counter()
        funcao(dados)
        melhor = min(melhor, time.perf_counter() - inicio)
    return melhor * 1000  # milissegundos


def main():
    rnd = random.Random(2026)
    algoritmos = {
        "merge_sort": lambda d: merge_sort(d, chave=chave),
        "insertion_sort": lambda d: insertion_sort(d, chave=chave),
        "sorted (Timsort)": lambda d: sorted(d, key=chave),
    }
    linhas = []
    print(f"{'n':>6} | " + " | ".join(f"{nome:>17}" for nome in algoritmos))
    for n in TAMANHOS:
        dados = gerar_itens(n, rnd)
        referencia = sorted(dados, key=chave)
        tempos = {}
        for nome, f in algoritmos.items():
            assert f(dados) == referencia, f"{nome} ordenou errado"
            tempos[nome] = medir(f, dados)
        linhas.append({"n": n, **tempos})
        print(f"{n:>6} | " + " | ".join(f"{tempos[nome]:>14.2f} ms" for nome in algoritmos))

    os.makedirs(PASTA, exist_ok=True)
    with open(os.path.join(PASTA, "benchmark.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["n", *algoritmos])
        w.writeheader()
        w.writerows(linhas)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=150)
    estilos = {"merge_sort": ("#1f6feb", "o"), "insertion_sort": ("#d1242f", "s"), "sorted (Timsort)": ("#2da44e", "^")}
    for nome in algoritmos:
        cor, marca = estilos[nome]
        ax.plot([l["n"] for l in linhas], [l[nome] for l in linhas], marker=marca, color=cor, label=nome, linewidth=2)
    ax.set_xlabel("Quantidade de títulos (n)")
    ax.set_ylabel("Tempo (ms) — escala logarítmica")
    ax.set_yscale("log")
    ax.grid(True, alpha=.3)
    ax.legend()
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA, "benchmark.png"))


if __name__ == "__main__":
    main()
