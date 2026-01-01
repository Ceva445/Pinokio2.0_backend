import os
import ssl
import urllib.parse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set.")

url_without_params, params = DATABASE_URL.split("?", 1) if "?" in DATABASE_URL else (DATABASE_URL, "")
query_args = urllib.parse.parse_qs(params)

connect_args = {}
if "sslmode" in query_args and query_args["sslmode"][0] == "require":
    ssl_context = ssl.create_default_context()
    connect_args["ssl"] = ssl_context


engine = create_async_engine(
    url_without_params.replace("postgresql://", "postgresql+asyncpg://"),
    echo=True,
    connect_args=connect_args
)

async_session = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    async with async_session() as session:
        yield session