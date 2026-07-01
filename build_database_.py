
import sqlite3
conn = sqlite3.connect('guardian_rankings.db')
print('=== guardian_ranking ===')
for r in conn.execute('PRAGMA table_info(guardian_ranking)'):
    print(r)  # zobrazí (cid, name, type, notnull, dflt_value, pk)
print()
print('=== guardian_subject_areas ===')
for r in conn.execute('PRAGMA table_info(guardian_subject_areas)'):
    print(r)
conn.close()
