-- Função para atualizar timestamp automaticamente
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers para atualizar automaticamente o campo atualizado_em
CREATE TRIGGER update_ofertas_updated_at 
    BEFORE UPDATE ON ofertas 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_agendamentos_updated_at 
    BEFORE UPDATE ON agendamentos 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_alertas_updated_at 
    BEFORE UPDATE ON alertas 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_configuracoes_updated_at 
    BEFORE UPDATE ON configuracoes 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Função para calcular próxima execução de agendamento
CREATE OR REPLACE FUNCTION calcular_proxima_execucao(intervalo_horas INTEGER)
RETURNS TIMESTAMP AS $$
BEGIN
    RETURN NOW() + (intervalo_horas || ' hours')::INTERVAL;
END;
$$ language 'plpgsql';

-- Função para limpar ofertas antigas (mais de 30 dias)
CREATE OR REPLACE FUNCTION limpar_ofertas_antigas()
RETURNS INTEGER AS $$
DECLARE
    registros_removidos INTEGER;
BEGIN
    DELETE FROM ofertas 
    WHERE criado_em < NOW() - INTERVAL '30 days'
    AND id NOT IN (
        SELECT DISTINCT oferta_id 
        FROM produtos_aprovados 
        WHERE oferta_id IS NOT NULL
    );
    
    GET DIAGNOSTICS registros_removidos = ROW_COUNT;
    RETURN registros_removidos;
END;
$$ language 'plpgsql';
