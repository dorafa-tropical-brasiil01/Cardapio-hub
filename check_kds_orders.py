import os
import psycopg2

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:muoqdAqYHnnOmZhJPlLPJtAjWWYuMaKr@postgres.railway.internal:5432/railway')

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Verificar se tabela existe
try:
    cur.execute("SELECT COUNT(*) FROM kds_orders")
    count = cur.fetchone()[0]
    print(f"Registros kds_orders: {count}")
    
    if count > 0:
        cur.execute("SELECT solicitacao_id, status, created_em FROM kds_orders ORDER BY created_em DESC LIMIT 5")
        print("Últimos 5:")
        for row in cur.fetchall():
            print(row)
    else:
        print("Tabela kds_orders está vazia")
except Exception as e:
    print(f"Erro ao consultar kds_orders: {e}")

conn.close()
