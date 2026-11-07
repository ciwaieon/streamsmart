"""
Estruturas de dados e algoritmos implementados manualmente.

Este módulo concentra o conteúdo de Lógica de Programação e Estrutura de Dados
usado pelo sistema:

- MinHeap ............ fila de prioridade (heap binário mínimo) usada nos alertas de cobrança;
- merge_sort ......... ordenação O(n log n), estável, usada no recomendador e no relatório;
- insertion_sort ..... ordenação O(n²), usada apenas como comparação no benchmark;
- busca_binaria ...... busca O(log n) em lista ordenada.
"""


class MinHeap:
    """Fila de prioridade baseada em heap binário mínimo.

    O menor elemento fica sempre na raiz (posição 0). Para um nó na posição i:
    filho esquerdo = 2i + 1, filho direito = 2i + 2, pai = (i - 1) // 2.
    Inserir e remover custam O(log n); consultar o menor custa O(1).
    """

    def __init__(self):
        self._dados = []

    def __len__(self):
        return len(self._dados)

    def vazio(self):
        return len(self._dados) == 0

    def topo(self):
        if self.vazio():
            raise IndexError("heap vazio")
        return self._dados[0]

    def inserir(self, item):
        self._dados.append(item)
        self._subir(len(self._dados) - 1)

    def remover(self):
        """Remove e devolve o menor elemento."""
        if self.vazio():
            raise IndexError("heap vazio")
        menor = self._dados[0]
        ultimo = self._dados.pop()
        if self._dados:
            self._dados[0] = ultimo
            self._descer(0)
        return menor

    def _subir(self, i):
        while i > 0:
            pai = (i - 1) // 2
            if self._dados[i] < self._dados[pai]:
                self._dados[i], self._dados[pai] = self._dados[pai], self._dados[i]
                i = pai
            else:
                break

    def _descer(self, i):
        n = len(self._dados)
        while True:
            menor = i
            esq, dir_ = 2 * i + 1, 2 * i + 2
            if esq < n and self._dados[esq] < self._dados[menor]:
                menor = esq
            if dir_ < n and self._dados[dir_] < self._dados[menor]:
                menor = dir_
            if menor == i:
                break
            self._dados[i], self._dados[menor] = self._dados[menor], self._dados[i]
            i = menor


def _identidade(x):
    return x


def merge_sort(lista, chave=_identidade):
    """Ordena por intercalação (merge sort). Não altera a lista original.

    Divide a lista ao meio recursivamente até sobrarem listas de 1 elemento e
    depois intercala as metades já ordenadas. Complexidade O(n log n) em todos
    os casos. É estável: elementos com chaves iguais mantêm a ordem original.
    """
    if len(lista) <= 1:
        return list(lista)
    meio = len(lista) // 2
    esquerda = merge_sort(lista[:meio], chave)
    direita = merge_sort(lista[meio:], chave)
    return _intercalar(esquerda, direita, chave)


def _intercalar(esquerda, direita, chave):
    resultado = []
    i = j = 0
    while i < len(esquerda) and j < len(direita):
        # "<=" garante a estabilidade: em empate, o elemento da esquerda vem primeiro
        if chave(esquerda[i]) <= chave(direita[j]):
            resultado.append(esquerda[i])
            i += 1
        else:
            resultado.append(direita[j])
            j += 1
    resultado.extend(esquerda[i:])
    resultado.extend(direita[j:])
    return resultado


def insertion_sort(lista, chave=_identidade):
    """Ordenação por inserção. O(n²) no pior caso; usada só para comparação."""
    resultado = list(lista)
    for i in range(1, len(resultado)):
        atual = resultado[i]
        k = chave(atual)
        j = i - 1
        while j >= 0 and chave(resultado[j]) > k:
            resultado[j + 1] = resultado[j]
            j -= 1
        resultado[j + 1] = atual
    return resultado


def busca_binaria(lista_ordenada, alvo, chave=_identidade):
    """Retorna o índice de `alvo` na lista ordenada, ou -1 se não existir. O(log n)."""
    inicio, fim = 0, len(lista_ordenada) - 1
    while inicio <= fim:
        meio = (inicio + fim) // 2
        valor = chave(lista_ordenada[meio])
        if valor == alvo:
            return meio
        if valor < alvo:
            inicio = meio + 1
        else:
            fim = meio - 1
    return -1
