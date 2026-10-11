"""Builds database.db from the SQL files, in order.
Usage:  python build_db.py            # schema + sample data + reconciliation
        python build_db.py --no-seed  # schema only (load your own data, then run reconcile.sql)
"""
import os, sqlite3, sys
 
DB = "database.db"
steps = ["dbschema.sql"] + ([] if "--no-seed" in sys.argv else ["sampledata.sql", "reconcile.sql"])
 
if os.path.exists(DB):
    os.remove(DB)                      # start clean
conn = sqlite3.connect(DB)             # creates database.db
for f in steps:
    with open(f) as fh:
        conn.executescript(fh.read())
    print("ran", f)
conn.commit()
 
if len(steps) > 1:
    print("matches:   ", conn.execute("SELECT COUNT(*) FROM recon_match").fetchone()[0])
    print("exceptions:", conn.execute("SELECT COUNT(*) FROM recon_exception").fetchone()[0])
    for r in conn.execute("SELECT exception_type, severity, detail FROM recon_exception ORDER BY exception_id"):
        print("  ", *r)
conn.close()