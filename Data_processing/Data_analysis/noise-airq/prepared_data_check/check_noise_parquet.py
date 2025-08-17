import pandas as pd

df = pd.read_parquet(r"data\processed\noise_voice_1min.parquet")

print(df.shape)       # rows, columns
print(df.columns)     # list of columns
print(df.head(10))    # first 10 rows
