## ADDED Requirements

### Requirement: Integração de Logs e Fallback no Pipeline de Busca
O pipeline de unificação e busca (`buscar_e_salvar_ofertas`) DEVE orquestrar o registro de logs e a chamada de relaxamento de termos sem bloquear a resposta da API em caso de instabilidade.

#### Scenario: Execução resiliente da busca
- **WHEN** o usuário inicia uma pesquisa de ofertas
- **THEN** o pipeline monitora o tempo de execução, captura exceções e finaliza o log com métricas precisas
