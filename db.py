from supabase import create_client, Client
from utils.config import config
from loguru import logger

_client: Client = None

def get_db() -> Client:
    global _client
    if _client is None:
        if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_KEY:
            raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY")
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        logger.info("Supabase client initialized")
    return _client
