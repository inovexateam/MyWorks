"""
OraQuery Schema Fetcher
=======================
Connects to your Oracle DB and exports the full schema (tables, columns,
PKs, FKs) as a JSON file that the OraQuery HTML tool loads directly.

Requirements:
    pip install oracledb

Usage:
    python oracle_schema_fetch.py

Output:
    oracle_schema.json  ← drop this in the same folder as oracle_sql_builder.html
"""

import json
import sys
import getpass

try:
    import oracledb
except ImportError:
    print("Installing oracledb...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "oracledb"])
    import oracledb

# ================================================================
# CONNECTION CONFIG — edit these or leave blank to be prompted
# ================================================================
CONFIG = {
    # Option A: Easy connect string  e.g. "myhost:1521/ORCL"
    "dsn": "",

    # Option B: TNS alias (uses tnsnames.ora / ORACLE_HOME)
    "tns_alias": "",

    # Option C: Wallet / mTLS (ATP, Always Free, etc.)
    # Leave dsn as the host:port/service and set wallet_location
    "wallet_location": "",   # e.g. r"C:\oracle\wallet"

    # Credentials (leave blank to be prompted)
    "user": "",
    "password": "",

    # Schema owner to fetch (leave blank = current user's schema)
    # Use a comma-separated string to fetch multiple: "HR,SALES"
    "schema_owners": "",

    # Filter: only fetch these tables (leave blank = ALL tables)
    # e.g. "EMPLOYEES,DEPARTMENTS,JOBS"
    "table_filter": "",

    # Output file
    "output_file": "oracle_schema.json",
}

# ================================================================
# QUERIES
# ================================================================
TABLES_SQL = """
SELECT
    t.owner,
    t.table_name,
    t.num_rows,
    c.comments
FROM all_tables t
LEFT JOIN all_tab_comments c
    ON c.owner = t.owner AND c.table_name = t.table_name
WHERE t.owner IN ({owners})
  {table_filter}
ORDER BY t.owner, t.table_name
"""

COLUMNS_SQL = """
SELECT
    col.owner,
    col.table_name,
    col.column_name,
    col.data_type,
    col.data_length,
    col.data_precision,
    col.data_scale,
    col.nullable,
    col.column_id,
    col.data_default,
    cm.comments
FROM all_tab_columns col
LEFT JOIN all_col_comments cm
    ON cm.owner = col.owner
   AND cm.table_name = col.table_name
   AND cm.column_name = col.column_name
WHERE col.owner IN ({owners})
  {table_filter}
ORDER BY col.owner, col.table_name, col.column_id
"""

PK_SQL = """
SELECT
    c.owner,
    c.table_name,
    cc.column_name,
    cc.position
FROM all_constraints c
JOIN all_cons_columns cc
    ON cc.owner = c.owner
   AND cc.constraint_name = c.constraint_name
WHERE c.constraint_type = 'P'
  AND c.owner IN ({owners})
  {table_filter}
ORDER BY c.owner, c.table_name, cc.position
"""

FK_SQL = """
SELECT
    c.owner,
    c.table_name,
    cc.column_name,
    c.r_owner,
    rc.table_name  AS ref_table,
    rcc.column_name AS ref_column,
    c.delete_rule
FROM all_constraints c
JOIN all_cons_columns cc
    ON cc.owner = c.owner
   AND cc.constraint_name = c.constraint_name
JOIN all_constraints rc
    ON rc.owner = c.r_owner
   AND rc.constraint_name = c.r_constraint_name
JOIN all_cons_columns rcc
    ON rcc.owner = rc.owner
   AND rcc.constraint_name = rc.constraint_name
   AND rcc.position = cc.position
WHERE c.constraint_type = 'R'
  AND c.owner IN ({owners})
ORDER BY c.owner, c.table_name, cc.column_name
"""

VIEWS_SQL = """
SELECT
    v.owner,
    v.view_name,
    vc.comments
FROM all_views v
LEFT JOIN all_tab_comments vc
    ON vc.owner = v.owner AND vc.table_name = v.view_name
WHERE v.owner IN ({owners})
ORDER BY v.owner, v.view_name
"""

# ================================================================
# HELPERS
# ================================================================
def prompt(label, secret=False):
    if secret:
        return getpass.getpass(f"  {label}: ")
    return input(f"  {label}: ").strip()

def make_alias(name, existing_aliases):
    words = name.split('_')
    alias = ''.join(w[0] for w in words if w).upper()
    if len(alias) < 2:
        alias = name[:2].upper()
    candidate, n = alias, 2
    while candidate in existing_aliases:
        candidate = alias + str(n)
        n += 1
    return candidate

def fmt_type(row_type, length, precision, scale):
    t = row_type
    if t in ('VARCHAR2', 'NVARCHAR2', 'CHAR', 'NCHAR'):
        return f"{t}({length})"
    if t == 'NUMBER':
        if precision and scale:
            return f"NUMBER({precision},{scale})"
        if precision:
            return f"NUMBER({precision})"
        return "NUMBER"
    return t

# ================================================================
# MAIN
# ================================================================
def main():
    print("\n╔══════════════════════════════════════╗")
    print("║   OraQuery — Oracle Schema Fetcher   ║")
    print("╚══════════════════════════════════════╝\n")

    # --- Connection ---
    dsn = CONFIG["dsn"]
    user = CONFIG["user"]
    password = CONFIG["password"]
    wallet = CONFIG["wallet_location"]

    if not dsn and not CONFIG["tns_alias"]:
        print("Connection details:")
        dsn = prompt("Host:Port/Service  (e.g. localhost:1521/ORCL)")
    if CONFIG["tns_alias"] and not dsn:
        dsn = CONFIG["tns_alias"]

    if not user:
        user = prompt("Username")
    if not password:
        password = prompt("Password", secret=True)

    print(f"\n  Connecting to {dsn} as {user}...")

    try:
        if wallet:
            oracledb.init_oracle_client()  # thick mode for wallet
            conn = oracledb.connect(user=user, password=password, dsn=dsn,
                                    wallet_location=wallet, wallet_password=password)
        else:
            conn = oracledb.connect(user=user, password=password, dsn=dsn)
        print("  ✓ Connected\n")
    except Exception as e:
        print(f"\n  ✗ Connection failed: {e}")
        sys.exit(1)

    cursor = conn.cursor()

    # --- Schema owners ---
    schema_owners = CONFIG["schema_owners"]
    if not schema_owners:
        cursor.execute("SELECT SYS_CONTEXT('USERENV','CURRENT_SCHEMA') FROM dual")
        schema_owners = cursor.fetchone()[0]
        print(f"  Using current schema: {schema_owners}")

    owners = [o.strip().upper() for o in schema_owners.split(',')]
    owners_placeholder = ','.join(f"'{o}'" for o in owners)

    # --- Table filter ---
    table_filter_cfg = CONFIG["table_filter"]
    table_filter_sql = ""
    if table_filter_cfg:
        tbls = ','.join(f"'{t.strip().upper()}'" for t in table_filter_cfg.split(','))
        table_filter_sql = f"AND t.table_name IN ({tbls})"
        col_table_filter = f"AND col.table_name IN ({tbls})"
        pk_table_filter = f"AND c.table_name IN ({tbls})"
        fk_table_filter = f"AND c.table_name IN ({tbls})"
    else:
        col_table_filter = pk_table_filter = fk_table_filter = ""

    # --- Fetch tables ---
    print("  Fetching tables...")
    cursor.execute(TABLES_SQL.format(owners=owners_placeholder, table_filter=table_filter_sql))
    table_rows = cursor.fetchall()
    print(f"  ✓ {len(table_rows)} tables found")

    # --- Fetch columns ---
    print("  Fetching columns...")
    cursor.execute(COLUMNS_SQL.format(owners=owners_placeholder, table_filter=col_table_filter))
    col_rows = cursor.fetchall()
    print(f"  ✓ {len(col_rows)} columns found")

    # --- Fetch PKs ---
    print("  Fetching primary keys...")
    cursor.execute(PK_SQL.format(owners=owners_placeholder, table_filter=pk_table_filter))
    pk_rows = cursor.fetchall()
    pk_set = {(r[0], r[1], r[2]) for r in pk_rows}  # (owner, table, col)

    # --- Fetch FKs ---
    print("  Fetching foreign keys...")
    cursor.execute(FK_SQL.format(owners=owners_placeholder, table_filter=fk_table_filter))
    fk_rows = cursor.fetchall()
    # (owner, table, col, ref_owner, ref_table, ref_col, delete_rule)
    fk_map = {}
    for r in fk_rows:
        key = (r[0], r[1], r[2])
        fk_map[key] = f"{r[4]}.{r[5]}"

    # --- Build schema JSON ---
    print("\n  Building schema map...")
    tables_by_key = {}
    for r in table_rows:
        tables_by_key[(r[0], r[1])] = {
            "owner": r[0], "name": r[1], "num_rows": r[2],
            "comment": r[3] or "", "columns": []
        }

    for r in col_rows:
        key = (r[0], r[1])
        if key not in tables_by_key:
            continue
        col = {
            "name": r[2],
            "type": fmt_type(r[3], r[4], r[5], r[6]),
            "nullable": r[7] == 'Y',
            "pk": (r[0], r[1], r[2]) in pk_set,
            "fk": fk_map.get((r[0], r[1], r[2])),
            "comment": (r[10] or "").strip() or None,
        }
        tables_by_key[key]["columns"].append(col)

    # Assign aliases
    aliases = set()
    output_tables = []
    for tbl in tables_by_key.values():
        if not tbl["columns"]:
            continue
        alias = make_alias(tbl["name"], aliases)
        aliases.add(alias)
        output_tables.append({
            "name": tbl["name"],
            "owner": tbl["owner"],
            "alias": alias,
            "num_rows": tbl["num_rows"],
            "comment": tbl["comment"],
            "columns": tbl["columns"],
        })

    schema_json = {
        "meta": {
            "exported_by": user.upper(),
            "owners": owners,
            "table_count": len(output_tables),
            "total_columns": sum(len(t["columns"]) for t in output_tables),
            "relationship_count": len(fk_rows),
            "tool": "OraQuery Schema Fetcher v1.0"
        },
        "tables": output_tables
    }

    out_file = CONFIG["output_file"]
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(schema_json, f, indent=2, default=str)

    print(f"\n╔══════════════════════════════════════════╗")
    print(f"║  ✓ Schema exported: {out_file:<21}║")
    print(f"║  Tables  : {len(output_tables):<31}║")
    print(f"║  Columns : {sum(len(t['columns']) for t in output_tables):<31}║")
    print(f"║  FK Rels : {len(fk_rows):<31}║")
    print(f"╚══════════════════════════════════════════╝")
    print(f"\n  → Place oracle_schema.json next to oracle_sql_builder.html")
    print(f"  → Open the HTML tool → click 'Import DDL' → 'Load JSON Schema'\n")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()