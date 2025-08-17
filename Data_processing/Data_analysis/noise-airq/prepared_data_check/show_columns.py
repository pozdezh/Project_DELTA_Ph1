import sqlite3
import pandas as pd
import yaml

db_path = r"X:\TFG_extra\EXPERIMENT_DATA\database_exp\experiment_1_data.db"
yaml_path = "config/time_window_unified.yaml"

with open(yaml_path, "r") as f:
    cfg = yaml.safe_load(f)

start_local = cfg["window"]["local"]["start"]
end_local   = cfg["window"]["local"]["end"]

conn = sqlite3.connect(db_path)
query = f"""
SELECT *
FROM airq_raw
WHERE created_at BETWEEN '{start_local}' AND '{end_local}'
LIMIT 20;
"""
df_airq = pd.read_sql(query, conn)
print(df_airq.head())

start_epoch = cfg["window"]["epoch_utc"]["start"]
end_epoch   = cfg["window"]["epoch_utc"]["end"]

query = f"""
SELECT *
FROM noise_spectrum_long
WHERE ts_unix BETWEEN {start_epoch} AND {end_epoch}
LIMIT 20;
"""
df_spec = pd.read_sql(query, conn)
print(df_spec.head())
