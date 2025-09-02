
import sys
import pandas as pd

if len(sys.argv) < 3:
    print("Usage: python convert_csv_to_parquet.py <input.csv> <output.parquet>")
    sys.exit(1)

inp, outp = sys.argv[1], sys.argv[2]
df = pd.read_csv(inp, parse_dates=["ts_min_utc"])
df.to_parquet(outp, index=False)  # requires: pip install pyarrow
print(f"Converted {inp} -> {outp}")
