import sqlite3
con = sqlite3.connect("uc3.db")
for table in ["review_decisions", "flags", "run_traces"]:
    print(f"=== {table} ===")
    for col in con.execute(f"PRAGMA table_info({table})"):
        print(" ", col[1])
