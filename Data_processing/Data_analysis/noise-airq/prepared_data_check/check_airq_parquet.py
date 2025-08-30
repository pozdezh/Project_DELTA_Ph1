# import pandas as pd

# # Load parquet
# df = pd.read_parquet(r"data\processed\airq_temp_hum_1min.parquet")

# # Show shape and first rows
# print("Shape:", df.shape)
# print("\nHead:")
# print(df.head(10))

# # Show kits and parameters included
# print("\nUnique kits:", df["kit_code"].unique())
# print("Parameters:", df["id_parameter"].unique() if "id_parameter" in df.columns else "not present")

# # Quick stats
# print("\nDescribe:")
# print(df.describe(include="all"))

import pandas as pd

df = pd.read_parquet(r"data\processed\airq_1min.parquet")

print(df.shape)       # rows, columns
print(df.columns)     # list of columns
print(df.head(10))    # first 10 rows