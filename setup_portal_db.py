import os
import csv
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 5433))
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")  # set DB_PASSWORD env var (kept out of git)
DB_NAME = os.environ.get("DB_NAME_SUB", "nse_subscription")

def create_database(db_name):
    print(f"Connecting to PostgreSQL as '{DB_USER}' to ensure database '{db_name}' exists...")
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname="postgres"
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    
    # Check if DB exists
    cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s;", (db_name,))
    exists = cur.fetchone()
    if not exists:
        print(f"Database '{db_name}' does not exist. Creating...")
        cur.execute(f"CREATE DATABASE {db_name};")
        print(f"Database '{db_name}' created successfully.")
    else:
        print(f"Database '{db_name}' already exists.")
        
    cur.close()
    conn.close()

def run_migrations():
    print(f"Connecting to database '{DB_NAME}' to run migrations...")
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME
    )
    cur = conn.cursor()
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    migrations_dir = os.path.join(base_dir, "nse-website", "subscription-portal", "database", "migrations")
    migration_files = sorted([f for f in os.listdir(migrations_dir) if f.endswith(".sql")])
    
    for file_name in migration_files:
        file_path = os.path.join(migrations_dir, file_name)
        print(f"Applying migration: {file_name}...")
        with open(file_path, "r", encoding="utf-8") as f:
            sql = f.read()
            if sql.strip():
                try:
                    cur.execute(sql)
                    conn.commit()
                    print(f"Successfully applied {file_name}")
                except Exception as e:
                    conn.rollback()
                    print(f"Error applying {file_name}: {e}")
                    # If table already exists, we can proceed
                    if "already exists" in str(e):
                        print("Table already exists. Continuing...")
                    else:
                        raise e

    # Apply plans seed
    plans_seed_path = os.path.join(base_dir, "nse-website", "subscription-portal", "database", "seed", "plans.sql")
    if os.path.exists(plans_seed_path):
        print("Applying plans seed...")
        with open(plans_seed_path, "r", encoding="utf-8") as f:
            sql = f.read()
            if sql.strip():
                try:
                    cur.execute(sql)
                    conn.commit()
                    print("Successfully seeded plans.")
                except Exception as e:
                    conn.rollback()
                    print(f"Plans seed note/error: {e} (Continuing...)")
    
    # Apply companies CSV seed
    companies_csv_path = os.path.join(base_dir, "nse-website", "subscription-portal", "database", "seed", "companies.csv")
    if os.path.exists(companies_csv_path):
        print("Applying companies seed from CSV...")
        with open(companies_csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)  # skip header
            count = 0
            for row in reader:
                if len(row) >= 2:
                    symbol, company_name = row[0].strip(), row[1].strip()
                    try:
                        cur.execute(
                            "INSERT INTO companies (symbol, company_name) VALUES (%s, %s) ON CONFLICT (symbol) DO NOTHING;",
                            (symbol, company_name)
                        )
                        count += 1
                    except Exception as e:
                        print(f"Error inserting company {symbol}: {e}")
            conn.commit()
            print(f"Successfully seeded {count} companies.")

    cur.close()
    conn.close()
    print("Database setup completed successfully!")

if __name__ == "__main__":
    try:
        create_database("nse_subscription")
        create_database("nse_ingestion")
        run_migrations()
    except Exception as e:
        print(f"❌ Database Setup Failed: {e}")
