import os
from sqlalchemy import create_engine, text

engine = create_engine(os.getenv("AEGIS_DATABASE_URL"))

with engine.begin() as c:
    print("Current DB:", c.execute(text("select current_database()")).fetchone())

    cols = c.execute(text("""
        SELECT column_name 
        FROM information_schema.columns
        WHERE table_name='aegis_semantic_contracts'
    """)).fetchall()

    print("Columns:", cols)
