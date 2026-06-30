import psycopg2

conn = psycopg2.connect(
    dbname="postgres",
    user="postgres",
    password="Kaizoku",
    host="localhost",
    port=5432
)

cur = conn.cursor()
cur.execute("ALTER USER postgres WITH PASSWORD 'aegis';")
conn.commit()
cur.close()
conn.close()

print("Postgres password reset to 'aegis'")
