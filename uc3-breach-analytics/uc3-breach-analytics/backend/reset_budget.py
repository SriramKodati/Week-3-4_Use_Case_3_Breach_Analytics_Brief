import sqlite3
con = sqlite3.connect("uc3.db")
con.execute("update runs set token_budget = 200000, status = 'running'")
con.commit()
print("reset")
