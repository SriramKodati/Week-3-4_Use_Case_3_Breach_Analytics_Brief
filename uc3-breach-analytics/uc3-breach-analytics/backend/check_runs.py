import sqlite3
con = sqlite3.connect("uc3.db")
print("=== runs columns ===")
for col in con.execute("PRAGMA table_info(runs)"):
    print(" ", col[1])
print("=== runs rows ===")
for row in con.execute("select * from runs"):
    print(" ", row)
print("=== documents run_id ===")
for row in con.execute("select filename, run_id, status from documents"):
    print(" ", row)
