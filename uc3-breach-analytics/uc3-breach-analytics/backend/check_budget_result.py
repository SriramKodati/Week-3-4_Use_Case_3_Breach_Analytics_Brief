import sqlite3
con = sqlite3.connect("uc3.db")
print("=== runs ===")
for row in con.execute("select id, status, tokens_used_total, token_budget from runs"):
    print(row)
print("=== recent documents ===")
for row in con.execute("select filename, status, quarantine_reason from documents order by uploaded_at desc limit 3"):
    print(row)
print("=== recent run_traces ===")
for row in con.execute("select agent_or_component, tool_call_name, input_summary, output_summary from run_traces order by created_at desc limit 5"):
    print(row)
