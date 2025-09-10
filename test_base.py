import os, sys
from contextlib import closing

def load_env_and_show():
    try:
        from dotenv import load_dotenv, find_dotenv
        load_dotenv(find_dotenv(usecwd=True))
    except Exception:
        pass
    vals = {
        "DB_HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "DB_PORT": os.getenv("DB_PORT", "5432"),
        "DB_NAME": os.getenv("DB_NAME"),
        "DB_USER": os.getenv("DB_USER"),
        "DB_PASSWORD": os.getenv("DB_PASSWORD"),
    }
    print("INFO: DB params in use:")
    print(f"  DB_HOST={vals['DB_HOST']}")
    print(f"  DB_PORT={vals['DB_PORT']}")
    print(f"  DB_NAME={vals['DB_NAME']}")
    print(f"  DB_USER={vals['DB_USER']}")
    print(f"  DB_PASSWORD={'***' if vals['DB_PASSWORD'] else '(empty)'}")
    return vals

def connect(vals):
    dsn = f"host={vals['DB_HOST']} port={vals['DB_PORT']} dbname={vals['DB_NAME']} user={vals['DB_USER']} password={vals['DB_PASSWORD']}"
    try:
        import psycopg
        return psycopg.connect(dsn, autocommit=True)
    except Exception:
        import psycopg2
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        return conn

def main():
    vals = load_env_and_show()
    try:
        with closing(connect(vals)) as conn, conn.cursor() as cur:
            cur.execute("SELECT current_user, current_database(), version();")
            u, d, v = cur.fetchone()
            print("OK: connected")
            print(f"  current_user    = {u}")
            print(f"  current_database= {d}")
            print(f"  version         = {v.splitlines()[0]}")
            # пошагово, без нескольких стейтментов в одной команде
            cur.execute("CREATE TEMP TABLE __t(i int);")
            cur.execute("INSERT INTO __t(i) VALUES (1);")
            cur.execute("SELECT COUNT(*) FROM __t;")
            cnt = cur.fetchone()[0]
            print(f"OK: temp table write/read = {cnt} row(s)")
            sys.exit(0)
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
