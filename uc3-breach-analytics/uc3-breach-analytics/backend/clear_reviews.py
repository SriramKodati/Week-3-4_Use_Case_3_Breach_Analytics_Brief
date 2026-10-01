import sqlite3
con = sqlite3.connect("uc3.db")
con.execute("delete from review_decisions")
con.commit()
print("cleared old review_decisions")
