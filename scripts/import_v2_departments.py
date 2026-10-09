"""Convert v2's Gov_Main_List.xlsx into data/departments_v2.csv, tagging which RSS parameter each code fits.

deptId must be 4 digits and deptsubId 10 digits (manual 3.1.2). Excel dropped leading zeros, so codes
of 1-4 digits are zero-padded back to 4. Other lengths do not match either format and are tagged "unknown".
"""
import csv
import os
import sys

import pandas as pd

src = sys.argv[1]
dst = os.path.join(os.path.dirname(__file__), "..", "data", "departments_v2.csv")

df = pd.read_excel(src, dtype=str)
rows = []
for _, r in df.iterrows():
    code = str(r["รหัสหน่วยงาน"]).strip().removesuffix(".0")
    if not code.isdigit():
        continue
    if len(code) <= 4:
        code, param = code.zfill(4), "deptId"
    elif len(code) == 10:
        param = "deptsubId"
    else:
        param = "unknown"
    rows.append({"code": code, "name": str(r["ชื่อหน่วยงาน"]).strip(), "param": param})

os.makedirs(os.path.dirname(dst), exist_ok=True)
with open(dst, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["code", "name", "param"])
    w.writeheader()
    w.writerows(rows)
print(pd.Series([r["param"] for r in rows]).value_counts().to_string())
