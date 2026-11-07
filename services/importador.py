"""
Importação automática do catálogo, em segundo plano.

Duas fontes, nesta ordem de prioridade:

1. Streaming Availability API (fonte principal): catálogo de cada streaming no Brasil, com
   dublado/legendado, qualidade, link direto e data de saída. Respeita a cota diária
   (100 consultas no plano gratuito) e continua de onde parou no dia seguinte.
2. TMDB (complemento): título e sinopse em português e classificação indicativa dos títulos
   acima, além de cobrir plataformas que a fonte principal não acompanha.

O usuário do site não faz nada. As chaves são configuradas uma única vez pelo desenvolvedor:
- streaming_chave.txt (ou variável STREAMING_CHAVE) para a Streaming Availability API;
- tmdb_chave.txt (ou variável TMDB_CHAVE) para o TMDB.
Os dois arquivos ficam fora do GitHub (.gitignore).
"""
import os
import threading
import time
from datetime import datetime, timedelta

import database
import repositorio as repo
from services import streaming
from services.tmdb import ClienteTMDB, ErroTMDB, importar as importar_tmdb

ARQUIVO_CHAVE = os.path.join(database.BASE_DIR, "tmdb_chave.txt")
ARQUIVO_CHAVE_STREAMING = os.path.join(database.BASE_DIR, "streaming_chave.txt")
DIAS_PARA_ATUALIZAR = 7
INTERVALO_HORAS = 6
FASES = [("rápida", 3), ("completa", 20)]

_trava = threading.Lock()
_rodando = threading.Event()
_laco_iniciado = False


def _ler_arquivo(caminho):
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha and not linha.startswith("#"):
                    return linha
    return None


def obter_chave(con):
    """Chave do TMDB."""
    return (os.environ.get("TMDB_CHAVE") or "").strip() or _ler_arquivo(ARQUIVO_CHAVE) or repo.ler_config(con, "tmdb_chave")


def obter_chave_streaming(con):
    return ((os.environ.get("STREAMING_CHAVE") or "").strip() or _ler_arquivo(ARQUIVO_CHAVE_STREAMING)
            or repo.ler_config(con, "streaming_chave"))


def limite_diario():
    try:
        return max(int(os.environ.get("STREAMING_LIMITE_DIARIO", 95)), 1)
    except ValueError:
        return 95


def status(con):
    return {
        "situacao": repo.ler_config(con, "tmdb_status") or "parado",
        "progresso": int(repo.ler_config(con, "tmdb_progresso") or 0),
        "mensagem": repo.ler_config(con, "tmdb_mensagem") or "",
        "ultima": repo.ler_config(con, "tmdb_ultima_importacao"),
        "rodando": _rodando.is_set(),
        "streaming": {
            "situacao": repo.ler_config(con, "streaming_status") or "parado",
            "mensagem": repo.ler_config(con, "streaming_mensagem") or "",
            "uso_hoje": streaming.uso_hoje(con),
            "limite": limite_diario(),
            "ciclo_completo": repo.ler_config(con, "streaming_ciclo_completo"),
        },
    }


def precisa_atualizar(con):
    """O complemento do TMDB precisa rodar? (nunca rodou ou faz mais de 7 dias)"""
    ultima = repo.ler_config(con, "tmdb_ultima_importacao")
    if not ultima or repo.contar_catalogo(con)["tmdb"] == 0:
        return True
    try:
        return datetime.now() - datetime.fromisoformat(ultima) > timedelta(days=DIAS_PARA_ATUALIZAR)
    except ValueError:
        return True


def _gravar(con, situacao, progresso, mensagem):
    repo.salvar_config(con, "tmdb_status", situacao)
    repo.salvar_config(con, "tmdb_progresso", str(progresso))
    repo.salvar_config(con, "tmdb_mensagem", mensagem)


def _gravar_streaming(con, situacao, mensagem):
    repo.salvar_config(con, "streaming_status", situacao)
    repo.salvar_config(con, "streaming_mensagem", mensagem)


def executar_streaming(con, cliente=None, cliente_tmdb=None):
    """Fonte principal: lê os catálogos dos streamings até gastar a cota do dia."""
    chave = obter_chave_streaming(con)
    if not chave and cliente is None:
        _gravar_streaming(con, "sem_chave", "Chave da Streaming Availability API não configurada.")
        return None
    # ciclo completo há mais de 7 dias: recomeça para atualizar disponibilidade, áudios e legendas
    ciclo = repo.ler_config(con, "streaming_ciclo_completo")
    if ciclo:
        try:
            if datetime.now() - datetime.fromisoformat(ciclo) > timedelta(days=DIAS_PARA_ATUALIZAR):
                streaming.reiniciar_ciclo(con)
                repo.salvar_config(con, "streaming_ciclo_completo", "")
        except ValueError:
            pass
    cliente = cliente or streaming.ClienteStreaming(chave)
    if cliente_tmdb is None and obter_chave(con):
        cliente_tmdb = ClienteTMDB(obter_chave(con))
    _gravar_streaming(con, "importando", "Lendo os catálogos dos streamings")

    def progresso(msg, feitas, total):
        _gravar_streaming(con, "importando", f"{msg} ({feitas} de {total} catálogos completos)")

    try:
        r = streaming.importar(con, cliente, limite_diario=limite_diario(), cliente_tmdb=cliente_tmdb, progresso=progresso)
    except streaming.ErroStreaming as e:
        _gravar_streaming(con, "erro", str(e))
        return None
    if r["completo"]:
        _gravar_streaming(con, "pronto", "Catálogos de todos os streamings lidos por completo.")
    elif r["cota_esgotada"]:
        _gravar_streaming(con, "pausado", f"Cota de hoje usada ({r['novos']} novos, {r['atualizados']} atualizados). Continua amanhã.")
    else:
        _gravar_streaming(con, "pronto", f"{r['novos']} títulos novos, {r['atualizados']} atualizados.")
    return r


def executar(caminho_db=None, forcar=False, fases=FASES, cliente=None, cliente_streaming=None):
    """Roda uma rodada de importação (bloqueante). Usada pela thread e pelos testes.

    Devolve True se o complemento do TMDB rodou.
    """
    if not _trava.acquire(blocking=False):
        return False                                   # já existe uma importação em andamento
    _rodando.set()
    con = database.conectar(caminho_db)
    try:
        # 1) fonte principal
        executar_streaming(con, cliente=cliente_streaming, cliente_tmdb=cliente)
        # 2) complemento do TMDB
        chave = obter_chave(con)
        if not chave and cliente is None:
            _gravar(con, "sem_chave", 0, "Chave do TMDB não configurada.")
            return False
        if not forcar and not precisa_atualizar(con):
            _gravar(con, "pronto", 100, "Catálogo atualizado.")
            return False
        cliente = cliente or ClienteTMDB(chave)
        for i, (nome, paginas) in enumerate(fases):
            inicio, fim = i * 100 // len(fases), (i + 1) * 100 // len(fases)

            def progresso(msg, pct, inicio=inicio, fim=fim, nome=nome):
                if pct is not None:
                    _gravar(con, "importando", inicio + pct * (fim - inicio) // 100, f"Carga {nome}: {msg}")

            importar_tmdb(con, cliente, paginas=paginas, progresso=progresso)
            repo.salvar_config(con, "tmdb_ultima_importacao", datetime.now().isoformat(timespec="seconds"))
        _gravar(con, "pronto", 100, "Catálogo atualizado.")
        return True
    except ErroTMDB as e:
        _gravar(con, "erro", 0, str(e))
        return False
    finally:
        con.close()
        _rodando.clear()
        _trava.release()


def iniciar_em_segundo_plano(caminho_db=None, forcar=False):
    """Dispara a importação numa thread e repete a cada 6 horas, sem travar o site."""
    global _laco_iniciado
    if forcar:
        if not _rodando.is_set():
            threading.Thread(target=executar, kwargs={"caminho_db": caminho_db, "forcar": True},
                             name="importacao-forcada", daemon=True).start()
        return
    if _laco_iniciado:
        return
    _laco_iniciado = True

    def laco():
        while True:
            executar(caminho_db)
            time.sleep(INTERVALO_HORAS * 3600)

    threading.Thread(target=laco, name="importacao-catalogo", daemon=True).start()
