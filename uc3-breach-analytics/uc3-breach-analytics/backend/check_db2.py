import sqlite3
con = sqlite3.connect("uc3.db")

print("=== documents ===")
for col in con.execute("PRAGMA table_info(documents)"):
    print(" ", col[1])
for row in con.execute("select filename, status from documents"):
    print(" ", row)

print("\n=== flags ===")
for col in con.execute("PRAGMA table_info(flags)"):
    print(" ", col[1])
for row in con.execute("select * from flags"):
    print(" ", row)
