import os, pandas as pd, sqlalchemy
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = r'd:\1 Downloads\alert-palace-504123-t8-d996fe0ffbbc.json'
engine = sqlalchemy.create_engine('bigquery://alert-palace-504123-t8')
query = "SELECT T1.nome, SUM(T2.homicidio_doloso) AS total_homicidios FROM basedosdados.br_bd_diretorios_brasil.municipio AS T1 JOIN basedosdados.br_fbsp_anuario_seguranca_publica.municipio AS T2 ON T1.id_municipio = T2.id_municipio WHERE T1.sigla_uf = 'BA' GROUP BY T1.nome ORDER BY total_homicidios DESC LIMIT 10"
try:
    df = pd.read_sql(query, engine)
    print("Sucesso!")
    print(df)
except Exception as e:
    print('ERROR:', e)
