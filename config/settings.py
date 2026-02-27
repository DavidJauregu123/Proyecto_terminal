import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Configuración de la aplicación"""
    
    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
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
