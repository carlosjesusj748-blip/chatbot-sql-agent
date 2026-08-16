from google.cloud import bigquery

client = bigquery.Client(project="alert-palace-504123-t8")

# Descobrir colunas da tabela FBSP municipio
q1 = """
SELECT column_name, data_type
FROM `basedosdados.br_fbsp_absp.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'municipio'
ORDER BY ordinal_position
"""
print("=== br_fbsp_absp.municipio ===")
for row in client.query(q1).result():
    print(f"  {row.column_name} ({row.data_type})")

# Descobrir colunas do SIM/DATASUS
q2 = """
SELECT column_name, data_type
FROM `basedosdados.br_ms_sim.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'microdados'
ORDER BY ordinal_position
LIMIT 30
"""
print("\n=== br_ms_sim.microdados (primeiras 30) ===")
for row in client.query(q2).result():
    print(f"  {row.column_name} ({row.data_type})")
