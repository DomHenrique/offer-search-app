from database.supabase_client import SupabaseDB
from scraping.unificar_dados import unificar_dados_amazon_mercadolivre
from dotenv import load_dotenv 
import os

load_dotenv()


API_KEY = os.getenv("SERPAPI_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Busca dados
df_final = unificar_dados_amazon_mercadolivre("celular", API_KEY, paginas_ml=1)

# Salva no Supabase
db = SupabaseDB(SUPABASE_URL, SUPABASE_KEY)
db.salvar_ofertas(df_final)
