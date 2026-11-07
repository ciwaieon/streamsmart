-- StreamSmart - Esquema do banco de dados (SQLite)
-- Projeto Integrador: Laboratório de Programação - UNISA

PRAGMA foreign_keys = ON;

-- Usuários do sistema (RF01)
CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nome          TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    senha_hash    TEXT    NOT NULL,
    criado_em     TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Tokens de recuperação de senha (RF01)
CREATE TABLE IF NOT EXISTS tokens_recuperacao (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    token       TEXT    NOT NULL UNIQUE,
    expira_em   TEXT    NOT NULL,
    usado       INTEGER NOT NULL DEFAULT 0
);

-- Plataformas de streaming conhecidas
CREATE TABLE IF NOT EXISTS plataformas (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    nome  TEXT NOT NULL UNIQUE,
    cor   TEXT NOT NULL
);

-- Assinaturas do usuário (RF02)
CREATE TABLE IF NOT EXISTS assinaturas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    plataforma_id   INTEGER NOT NULL REFERENCES plataformas(id),
    plano           TEXT    NOT NULL,
    valor           REAL    NOT NULL CHECK (valor >= 0),
    periodicidade   TEXT    NOT NULL CHECK (periodicidade IN ('mensal', 'anual')),
    dia_vencimento  INTEGER NOT NULL CHECK (dia_vencimento BETWEEN 1 AND 31),
    mes_vencimento  INTEGER CHECK (mes_vencimento BETWEEN 1 AND 12),  -- usado apenas nos planos anuais
    fim_teste       TEXT,             -- data (AAAA-MM-DD) em que o teste grátis termina
    criado_em       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (usuario_id, plataforma_id)
);

-- Catálogo de filmes e séries (RF05)
CREATE TABLE IF NOT EXISTS titulos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo         TEXT    NOT NULL,
    tipo           TEXT    NOT NULL CHECK (tipo IN ('filme', 'serie')),
    ano            INTEGER,
    duracao_min    INTEGER NOT NULL,   -- filme: duração total; série: duração média do episódio
    generos        TEXT    NOT NULL,   -- separados por vírgula
    vibes          TEXT    NOT NULL,   -- separadas por vírgula: rir, suspense, emocao, leve
    classificacao  TEXT,               -- L, 10, 12, 14, 16, 18 ou NULL (sem informação)
    sinopse        TEXT    NOT NULL,
    tmdb_id        INTEGER,            -- identificador no The Movie Database
    poster_url     TEXT,               -- endereço da imagem do pôster (TMDB)
    nota_tmdb      REAL,               -- nota média no TMDB (0 a 10)
    origem         TEXT    NOT NULL DEFAULT 'demo'   -- 'demo' (catálogo local) ou 'tmdb'
);

-- Em quais plataformas cada título está disponível (relação N:N)
CREATE TABLE IF NOT EXISTS titulo_plataforma (
    titulo_id      INTEGER NOT NULL REFERENCES titulos(id) ON DELETE CASCADE,
    plataforma_id  INTEGER NOT NULL REFERENCES plataformas(id) ON DELETE CASCADE,
    PRIMARY KEY (titulo_id, plataforma_id)
);

-- Histórico do que o usuário assistiu (RF07)
CREATE TABLE IF NOT EXISTS historico (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    titulo_id       INTEGER NOT NULL REFERENCES titulos(id),
    plataforma_id   INTEGER NOT NULL REFERENCES plataformas(id),
    data            TEXT    NOT NULL,   -- AAAA-MM-DD
    minutos         INTEGER NOT NULL CHECK (minutos > 0)
);

-- Avaliações dos usuários (RF09)
CREATE TABLE IF NOT EXISTS avaliacoes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    titulo_id   INTEGER NOT NULL REFERENCES titulos(id) ON DELETE CASCADE,
    nota        INTEGER NOT NULL CHECK (nota BETWEEN 1 AND 5),
    comentario  TEXT,
    criado_em   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (usuario_id, titulo_id)
);

-- Amizades entre usuários (RF10)
CREATE TABLE IF NOT EXISTS amizades (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    solicitante_id   INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    destinatario_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    status           TEXT    NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'aceita')),
    criado_em        TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (solicitante_id, destinatario_id),
    CHECK (solicitante_id <> destinatario_id)
);

-- Configurações do sistema (ex.: chave da API do TMDB)
CREATE TABLE IF NOT EXISTS configuracoes (
    chave  TEXT PRIMARY KEY,
    valor  TEXT
);

CREATE INDEX IF NOT EXISTS idx_assinaturas_usuario ON assinaturas(usuario_id);
CREATE INDEX IF NOT EXISTS idx_historico_usuario_data ON historico(usuario_id, data);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_titulo ON avaliacoes(titulo_id);
CREATE INDEX IF NOT EXISTS idx_amizades_destinatario ON amizades(destinatario_id);
