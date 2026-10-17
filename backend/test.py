import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

database_url = os.environ["DATABASE_URL"]
ssl_root_cert = os.environ["PGSSLROOTCERT"]

engine = create_engine(
    database_url,
    connect_args={
        "sslrootcert": ssl_root_cert
    }
)

with engine.connect() as conn:
    result = conn.execute(text("SELECT version()"))
    print("Connected successfully!")
    print(result.fetchone())