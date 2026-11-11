
"""Configurações do GlicoCheck."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Localiza o .env na pasta principal do projeto
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE)

# Configuração do banco de dados
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "glicocheck_v2"),
    "charset": "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
}

# Segurança Flask
SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY não configurada no arquivo .env")

# Configurações adicionais
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
PORT = int(os.getenv("PORT", "5000"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
