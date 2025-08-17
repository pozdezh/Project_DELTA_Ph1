#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lossless merger for TWO AirQ CSVs into one CSV, with no data changes.
- Preserves every row and every original column/value.
- Adds one column: 'kit_code' (AIRQ001 / AIRQ002).
- Output header = union of input headers (first-seen order), with 'kit_code' as the first column.
- Row order: all rows from CSV1 (tagged AIRQ001) followed by all rows from CSV2 (tagged AIRQ002).

HOW TO USE (Windows-friendly, no CLI needed):
1) Edit the CONFIG section below: set CSV1_PATH, CSV2_PATH, OUT_PATH.
2) Double-click this file (if .py is associated with Python) or run:
     py merge_airq_csvs_lossless_config.py
"""

# ========== CONFIG (edit these) ==========
CSV1_PATH = r"Z:\URV\UNIVER\5_2\TFG_1\EXPERIMENT_DATA\database_exp\delta001_data.csv"     # <-- put your AIRQ001 CSV here
CSV2_PATH = r"Z:\URV\UNIVER\5_2\TFG_1\EXPERIMENT_DATA\database_exp\delta002_data.csv"     # <-- put your AIRQ002 CSV here
OUT_PATH  = r"Z:\URV\UNIVER\5_2\TFG_1\EXPERIMENT_DATA\database_exp\total_airq.csv"  # <-- where to save the merged CSV

KIT1_CODE = "AIRQ001"
KIT2_CODE = "AIRQ002"
# ========================================

import csv, os, sys

def read_rows_any_encoding(path):
    # Try utf-8-sig first (handles BOM), then fallback to utf-8
    for enc in ("utf-8-sig", "utf-8"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = [row for row in reader]
            return fieldnames, rows
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("utf-8", b"", 0, 1, f"Cannot decode file: {path}")

def main():
    # Basic checks
    if not os.path.exists(CSV1_PATH):
        print(f"[ERROR] File not found: {CSV1_PATH}")
        return
    if not os.path.exists(CSV2_PATH):
        print(f"[ERROR] File not found: {CSV2_PATH}")
        return

    fn1, rows1 = read_rows_any_encoding(CSV1_PATH)
    fn2, rows2 = read_rows_any_encoding(CSV2_PATH)

    # Build union of headers, preserving first-seen order; put 'kit_code' first
    seen = set()
    headers = ["kit_code"]
    for name in (fn1 or []):
        if name not in seen:
            headers.append(name); seen.add(name)
    for name in (fn2 or []):
        if name not in seen:
            headers.append(name); seen.add(name)

    # Ensure output directory exists
    out_dir = os.path.dirname(OUT_PATH)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    # Write merged CSV
    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore", restval="")
        writer.writeheader()

        for r in rows1:
            r_out = dict(r)
            r_out["kit_code"] = KIT1_CODE
            writer.writerow(r_out)

        for r in rows2:
            r_out = dict(r)
            r_out["kit_code"] = KIT2_CODE
            writer.writerow(r_out)

    print(f"[OK] Wrote {OUT_PATH}")
    print(f"     Rows: {len(rows1) + len(rows2)}  |  Columns: {len(headers)}")
    print(f"     CSV1 ({KIT1_CODE}): {CSV1_PATH}  -> {len(rows1)} rows, {len(fn1)} cols")
    print(f"     CSV2 ({KIT2_CODE}): {CSV2_PATH}  -> {len(rows2)} rows, {len(fn2)} cols")

if __name__ == "__main__":
    main()
