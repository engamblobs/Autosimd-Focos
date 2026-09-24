import ijson
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import os

PATH_GEOJSON = "/home/lobs/SIG/FOCOS DE CALOR/bdqueimadas_consolidado.geojson"
PATH_PARQUET = "/home/lobs/SIG/FOCOS DE CALOR/bdqueimadas_consolidado.parquet"
BATCH_SIZE = 50000  # Grava no disco a cada 50.000 focos

print("Iniciando conversão em fluxo (streaming)...")

# Esquema fixo para o PyArrow evitar divergência de tipos entre lotes
schema = pa.schema([
    ('lon', pa.float64()),
    ('lat', pa.float64()),
    ('ano', pa.int32()),
    ('mes', pa.int32()),
    ('data', pa.string()),
    ('NM_MUN', pa.string()),
    ('NM_UF', pa.string()),
    ('SIGLA_UF', pa.string()),
    ('UC', pa.string()),
    ('TI', pa.string()),
])

writer = pq.ParquetWriter(PATH_PARQUET, schema, compression='snappy')
batch = []
total_processado = 0

with open(PATH_GEOJSON, "rb") as f:
    # Lê as features individualmente do JSON sem carregar o arquivo todo
    features = ijson.items(f, "features.item")
    
    for feat in features:
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        
        if geom and geom.get("type") == "Point":
            coords = geom.get("coordinates", [])
            if len(coords) >= 2:
                batch.append({
                    "lon": float(coords[0]),
                    "lat": float(coords[1]),
                    "ano": int(props.get("ano")) if props.get("ano") is not None else None,
                    "mes": int(props.get("mes")) if props.get("mes") is not None else None,
                    "data": str(props.get("data", "")),
                    "NM_MUN": str(props.get("NM_MUN", "")).strip().upper(),
                    "NM_UF": str(props.get("NM_UF", "")).strip().upper(),
                    "SIGLA_UF": str(props.get("SIGLA_UF", "")).strip().upper(),
                    "UC": str(props.get("UC", "")).strip().upper(),
                    "TI": str(props.get("TI", "")).strip().upper(),
                })
        
        # Grava o lote no arquivo Parquet e esvazia a memória RAM
        if len(batch) >= BATCH_SIZE:
            df_batch = pd.DataFrame(batch)
            table = pa.Table.from_pandas(df_batch, schema=schema)
            writer.write_table(table)
            total_processado += len(batch)
            print(f"Processados: {total_processado:,} registros...")
            batch = []

    # Grava o lote restante se houver
    if batch:
        df_batch = pd.DataFrame(batch)
        table = pa.Table.from_pandas(df_batch, schema=schema)
        writer.write_table(table)
        total_processado += len(batch)

writer.close()
print(f"✅ Sucesso! {total_processado:,} focos convertidos para: {PATH_PARQUET}")