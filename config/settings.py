import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Configuración de la aplicación"""
    
    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    
    # Database - Soporta DATABASE_URL o variables individuales
    _database_url = os.getenv("DATABASE_URL", "")
    if _database_url:
        DATABASE_URL = _database_url
    else:
        # Construir desde variables individuales
        db_user = os.getenv("DB_USER", "postgres")
        db_password = os.getenv("DB_PASSWORD", "")
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "proyecto_ideio")
        DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    # Gemini
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "True") == "True"
    
    # App Settings
    APP_NAME: str = "Sistema Experto Asesoría Curricular"
    APP_VERSION: str = "0.1.0"


def load_settings() -> Settings:
    """Carga la configuración de la aplicación"""
    return Settings()
