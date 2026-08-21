import os
import logging
from typing import Dict
import psycopg2
from psycopg2.extensions import connection
from database.db_manager import DatabaseManager

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TableManager:
    """Gerenciador para criação e verificação de tabelas no banco de dados"""
    
    def __init__(self, db_manager: DatabaseManager):
        """Inicializa o gerenciador de tabelas"""
        self.db_manager = db_manager
        self.supabase = db_manager.supabase
        self.table_definitions = self._load_table_definitions()
        # Tenta criar conexão direta com o banco de dados
        self.db_connection = None
        try:
            self.db_connection = self._create_db_connection()
        except Exception as e:
            logger.warning(f"⚠️ Não foi possível criar conexão direta com banco de dados: {e}")
            logger.info("ℹ️ Usando método alternativo de verificação de tabelas")
    
    def _create_db_connection(self) -> connection:
        """Cria uma conexão direta com o banco de dados PostgreSQL do Supabase"""
        try:
            # Extrai informações de conexão do URL do Supabase
            supabase_url = os.environ.get('SUPABASE_URL')
            db_password = os.environ.get('DATABASE_PASSWORD')
            
            if not supabase_url or not db_password:
                raise ValueError("SUPABASE_URL e DATABASE_PASSWORD são necessários para conexão direta")
            
            # Formato do URL do Supabase: https://[project-ref].supabase.co
            # Conexão PostgreSQL: postgresql://postgres:[project-ref]:5432/postgres
            # Precisamos converter o URL do Supabase para o formato de conexão PostgreSQL
            
            # Extrai o project-ref do URL
            project_ref = supabase_url.split('//')[1].split('.')[0]
            db_host = f"db.{project_ref}.supabase.co"
            db_port = 5432
            db_name = "postgres"
            db_user = "postgres"
            
            # Cria conexão direta com o banco de dados
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password
            )
            
            logger.info("✅ Conexão direta com banco de dados estabelecida")
            return conn
            
        except Exception as e:
            logger.error(f"❌ Erro ao criar conexão direta com banco de dados: {e}")
            raise
    
    def _load_table_definitions(self) -> Dict[str, str]:
        """Carrega as definições das tabelas a partir dos arquivos SQL"""
        table_definitions = {}
        script_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        
        table_scripts = {
            'users': '01_create_users_table.sql',
            'ofertas': '02_create_ofertas_table.sql',
            'produtos_aprovados': '03_create_produtos_aprovados_table.sql',
            'agendamentos': '04_create_agendamentos_table.sql',
            'historico_buscas': '05_create_historico_buscas_table.sql',
            'alertas': '06_create_alertas_table.sql',
            'configuracoes': '07_create_configuracoes_table.sql',
            'pedidos_compra': '08_create_pedidos_compra_e_itens.sql',
            'itens_pedido': '08_create_pedidos_compra_e_itens.sql'
        }
        
        for table_name, script_name in table_scripts.items():
            script_path = os.path.join(script_dir, script_name)
            try:
                if os.path.exists(script_path):
                    with open(script_path, 'r', encoding='utf-8') as f:
                        table_definitions[table_name] = f.read()
                        logger.info(f"✅ Definição da tabela '{table_name}' carregada com sucesso")
                else:
                    logger.warning(f"⚠️ Arquivo de script não encontrado: {script_path}")
            except Exception as e:
                logger.error(f"❌ Erro ao carregar script {script_name}: {e}")
        
        return table_definitions
    
    def table_exists(self, table_name: str) -> bool:
        """Verifica se uma tabela existe no banco de dados"""
        # Tenta usar conexão direta primeiro, se disponível
        if self.db_connection:
            try:
                cursor = self.db_connection.cursor()
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = %s
                    );
                """, (table_name,))
                
                exists = cursor.fetchone()[0]
                cursor.close()
                
                if exists:
                    logger.info(f"✅ Tabela '{table_name}' existe")
                else:
                    logger.warning(f"❌ Tabela '{table_name}' não encontrada")
                
                return exists
                
            except Exception as e:
                logger.error(f"❌ Erro ao verificar existência da tabela '{table_name}' via conexão direta: {e}")
        
        # Fallback: usa o cliente Supabase
        try:
            # Tenta fazer uma consulta simples para verificar se a tabela existe
            response = self.supabase.table(table_name).select("id").limit(1).execute()
            logger.info(f"✅ Tabela '{table_name}' existe")
            return True
        except Exception as e:
            error_msg = str(e).lower()
            # Se for um erro de tabela não encontrada, retorna False
            if "could not find the table" in error_msg or "does not exist" in error_msg:
                logger.warning(f"❌ Tabela '{table_name}' não encontrada")
                return False
            # Para outros erros, loga e assume que a tabela não existe
            logger.warning(f"⚠️ Erro ao verificar existência da tabela '{table_name}' via Supabase: {e}")
            return False
    
    def create_table(self, table_name: str) -> bool:
        """Cria uma tabela específica usando seu script SQL"""
        if table_name not in self.table_definitions:
            logger.error(f"❌ Definição da tabela '{table_name}' não encontrada")
            return False
        
        # Se tivermos conexão direta, usamos ela
        if self.db_connection:
            try:
                # Verifica se a tabela já existe
                if self.table_exists(table_name):
                    logger.info(f"ℹ️ Tabela '{table_name}' já existe")
                    return True
                
                # Executa o script de criação da tabela
                sql_script = self.table_definitions[table_name]
                
                cursor = self.db_connection.cursor()
                cursor.execute(sql_script)
                self.db_connection.commit()
                cursor.close()
                
                logger.info(f"✅ Tabela '{table_name}' criada com sucesso")
                return True
                
            except Exception as e:
                self.db_connection.rollback()
                error_msg = str(e)
                # Se for um erro de tabela já existente, loga como info
                if "already exists" in error_msg:
                    logger.info(f"ℹ️ Tabela '{table_name}' já existe")
                    return True
                else:
                    logger.error(f"❌ Erro ao criar tabela '{table_name}': {e}")
                    return False
        else:
            # Se não tivermos conexão direta, logamos um aviso
            logger.warning(f"⚠️ Não é possível criar tabela '{table_name}' automaticamente sem conexão direta ao banco")
            logger.info(f"ℹ️ Execute manualmente o script: scripts/{table_name}_create_table.sql")
            return False
    
    def create_all_tables(self) -> Dict[str, bool]:
        """Cria todas as tabelas necessárias"""
        results = {}
        logger.info("🚀 Iniciando criação de tabelas...")
        
        # Ordem de criação importante devido a dependências
        table_order = [
            'users',
            'ofertas',
            'produtos_aprovados',
            'agendamentos',
            'historico_buscas',
            'alertas',
            'configuracoes'
        ]
        
        for table_name in table_order:
            if table_name in self.table_definitions:
                logger.info(f"🔧 Criando tabela: {table_name}")
                success = self.create_table(table_name)
                results[table_name] = success
                if not success:
                    logger.error(f"❌ Falha ao criar tabela '{table_name}'")
            else:
                logger.warning(f"⚠️ Definição da tabela '{table_name}' não encontrada")
                results[table_name] = False
        
        # Verifica resultados
        success_count = sum(1 for result in results.values() if result)
        total_count = len(results)
        
        if success_count == total_count:
            logger.info(f"🎉 Todas as tabelas ({total_count}/{total_count}) foram criadas com sucesso!")
        else:
            logger.warning(f"⚠️ Apenas {success_count}/{total_count} tabelas foram criadas com sucesso")
        
        return results
    
    def verify_all_tables(self) -> Dict[str, bool]:
        """Verifica se todas as tabelas necessárias existem"""
        results = {}
        logger.info("🔍 Verificando existência das tabelas...")
        
        table_names = [
            'users',
            'ofertas',
            'produtos_aprovados',
            'agendamentos',
            'historico_buscas',
            'alertas',
            'configuracoes'
        ]
        
        for table_name in table_names:
            exists = self.table_exists(table_name)
            results[table_name] = exists
            if exists:
                logger.info(f"✅ Tabela '{table_name}' existe")
            else:
                logger.error(f"❌ Tabela '{table_name}' não encontrada")
        
        return results
    
    def close_connection(self):
        """Fecha a conexão com o banco de dados"""
        if self.db_connection:
            self.db_connection.close()
            logger.info("🔒 Conexão com banco de dados fechada")
        else:
            logger.info("ℹ️ Nenhuma conexão direta com banco de dados estava aberta")