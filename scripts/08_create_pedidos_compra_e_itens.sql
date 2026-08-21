-- ==============================================================================
-- Script 08: Criação das tabelas de Pedidos de Compra e Itens de Pedido (Estoque)
-- ==============================================================================

-- 1. Tabela de Pedidos de Compra (Lotes de Entrada)
CREATE TABLE IF NOT EXISTS public.pedidos_compra (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    numero_pedido TEXT NOT NULL,
    fornecedor TEXT,
    data_pedido TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    observacoes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- Índices para pedidos_compra
CREATE INDEX IF NOT EXISTS idx_pedidos_compra_user_id ON public.pedidos_compra(user_id);
CREATE INDEX IF NOT EXISTS idx_pedidos_compra_numero ON public.pedidos_compra(numero_pedido);

-- 2. Tabela de Itens do Pedido (Produtos / SKUs)
CREATE TABLE IF NOT EXISTS public.itens_pedido (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pedido_id UUID REFERENCES public.pedidos_compra(id) ON DELETE CASCADE,
    sku TEXT NOT NULL,
    descricao TEXT NOT NULL,
    ncm TEXT,
    quantidade INTEGER NOT NULL DEFAULT 1,
    preco_custo NUMERIC(12, 2),
    preco_revenda NUMERIC(12, 2),
    preco_site_pix NUMERIC(12, 2),
    link_produto TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- Índices para itens_pedido
CREATE INDEX IF NOT EXISTS idx_itens_pedido_pedido_id ON public.itens_pedido(pedido_id);
CREATE INDEX IF NOT EXISTS idx_itens_pedido_sku ON public.itens_pedido(sku);

-- RLS (Row Level Security)
ALTER TABLE public.pedidos_compra ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.itens_pedido ENABLE ROW LEVEL SECURITY;

-- Políticas de acesso público/anon para compatibilidade com a aplicação
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE schemaname = 'public' 
        AND tablename = 'pedidos_compra' 
        AND policyname = 'Allow all access to pedidos_compra'
    ) THEN
        CREATE POLICY "Allow all access to pedidos_compra" 
        ON public.pedidos_compra 
        FOR ALL 
        USING (true) 
        WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE schemaname = 'public' 
        AND tablename = 'itens_pedido' 
        AND policyname = 'Allow all access to itens_pedido'
    ) THEN
        CREATE POLICY "Allow all access to itens_pedido" 
        ON public.itens_pedido 
        FOR ALL 
        USING (true) 
        WITH CHECK (true);
    END IF;
END $$;
