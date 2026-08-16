import basedosdados as bd
import json

# Query para trazer o ID do dataset, ID da tabela e a descrição do que ela faz
query_metadados = """
SELECT 
    dataset_id, 
    table_id, 
    description 
FROM `basedosdados.br_bd_diretorios_brasil.tabela`
WHERE description IS NOT NULL
"""

print("Buscando metadados da Base dos Dados...")
# Lembre-se de por o ID do seu projeto Google Cloud configurado
df_meta = bd.read_sql(query_metadados, billing_project_id="seu-projeto-google-cloud")

# Converte para um formato de dicionário limpo
lista_tabelas = df_meta.to_dict(orient="records")

# Salva o arquivo localmente
with open("tabelas_metadados.json", "w", encoding="utf-8") as f:
    json.dump(lista_tabelas, f, ensure_ascii=False, indent=4)

print(f"Sucesso! {len(lista_tabelas)} tabelas mapeadas em 'tabelas_metadados.json'")
