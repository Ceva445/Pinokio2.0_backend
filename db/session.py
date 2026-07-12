import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


load_dotenv()

# Get database configuration from environment variables
db_user = os.getenv("POSTGRES_USER", "pinokio_user")
db_password = os.getenv("POSTGRES_PASSWORD", "pinokio_pass")
db_host = os.getenv("POSTGRES_HOST", "localhost")
db_port = os.getenv("POSTGRES_PORT", "5432")
db_name = os.getenv("POSTGRES_DB", "neondb")

# Construct DATABASE_URL from components
DATABASE_URL = f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

connect_args = {}


engine = create_async_engine(
    DATABASE_URL,
    # SQL logging toggled via .env: SQL_ECHO=true to see every query in the logs
    echo=os.getenv("SQL_ECHO", "false").lower() in ("1", "true", "yes"),
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=1800
)

async_session = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    async with async_session() as session:
        yield session