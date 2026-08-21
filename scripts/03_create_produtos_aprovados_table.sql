-- Tabela para armazenar produtos aprovados pelos usuários
CREATE TABLE produtos_aprovados (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    id_oferta TEXT NOT NULL,
    titulo TEXT NOT NULL,
    preco TEXT,
    preco_numerico NUMERIC(10, 2),
    url_produto TEXT,
    imagem TEXT,
    marketplace VARCHAR(50),
    termo_pesquisa TEXT,
    prime BOOLEAN DEFAULT FALSE,
    patrocinado BOOLEAN DEFAULT FALSE,
    desconto_percent INTEGER,
    preco_antigo TEXT,
    avaliacao NUMERIC(3, 2),
    avaliacoes INTEGER,
    categoria_preco VARCHAR(50),
    score_produto INTEGER,
    observacoes TEXT,
    link_afiliado TEXT, -- Novo campo para o link de afiliado
    aprovado_em TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, id_oferta)
);

-- Índices para otimizar consultas
CREATE INDEX idx_produtos_aprovados_user_id ON produtos_aprovados(user_id);
CREATE INDEX idx_produtos_aprovados_id_oferta ON produtos_aprovados(id_oferta);

-- Habilita RLS
ALTER TABLE produtos_aprovados ENABLE ROW LEVEL SECURITY;

-- Política: Usuários podem gerenciar seus próprios produtos aprovados
CREATE POLICY "user_can_manage_own_approved_products"
ON produtos_aprovados
FOR ALL
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);
