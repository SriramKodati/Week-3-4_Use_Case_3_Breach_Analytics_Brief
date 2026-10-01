import sqlite3
con = sqlite3.connect("uc3.db")
con.execute("update runs set token_budget = 50")
con.commit()
for row in con.execute("select id, status, tokens_used_total, token_budget from runs"):
    print(row)
