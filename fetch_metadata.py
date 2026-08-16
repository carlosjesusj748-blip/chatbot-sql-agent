import json
from google.cloud import bigquery
import os

PROJECT_ID = "alert-palace-504123-t8"
client = bigquery.Client(project=PROJECT_ID)

query = """
SELECT dataset_id, id_tabela as table_id, description 
FROM `basedosdados.br_bd_diretorios_brasil.tabela` 
WHERE description IS NOT NULL
"""

print("Buscando metadados da Base dos Dados...")
try:
    results = client.query(query).result()
    lista_tabelas = [dict(row) for row in results]
    
    with open("c:/Users/carlo/.gemini/antigravity-ide/scratch/chatbot-sql-agent/tabelas_metadados.json", "w", encoding="utf-8") as f:
        json.dump(lista_tabelas, f, ensure_ascii=False, indent=4)
        
    print(f"Sucesso! {len(lista_tabelas)} tabelas mapeadas.")
except Exception as e:
    # try with 'name' instead of 'id_tabela' just in case
    print(f"Error first try: {e}")
    try:
        query = "SELECT dataset_id, name as table_id, description FROM `basedosdados.br_bd_diretorios_brasil.tabela` WHERE description IS NOT NULL"
        results = client.query(query).result()
        lista_tabelas = [dict(row) for row in results]
        
        with open("c:/Users/carlo/.gemini/antigravity-ide/scratch/chatbot-sql-agent/tabelas_metadados.json", "w", encoding="utf-8") as f:
            json.dump(lista_tabelas, f, ensure_ascii=False, indent=4)
            
        print(f"Sucesso! {len(lista_tabelas)} tabelas mapeadas na tentativa 2.")
    except Exception as e2:
        print(f"Error: {e2}")
