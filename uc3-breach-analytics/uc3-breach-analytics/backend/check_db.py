import sqlite3
con = sqlite3.connect("uc3.db")

for table in ["persons", "identity_links", "extractions"]:
    print(f"\n=== {table} columns ===")
    for col in con.execute(f"PRAGMA table_info({table})"):
        print(" ", col[1])

print("\n=== persons rows ===")
for row in con.execute("select * from persons"):
    print(" ", row)

print("\n=== identity_links rows ===")
for row in con.execute("select * from identity_links"):
    print(" ", row)

print("\n=== extractions rows ===")
for row in con.execute("select category, raw_value, extraction_tier from extractions"):
    print(" ", row)
