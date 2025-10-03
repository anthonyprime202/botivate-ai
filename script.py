from dotenv import load_dotenv
import requests
import sqlite3
import os

load_dotenv()

def fetch_data_from_sheet(url):
    """Fetches and parses JSON data from the Google Apps Script URL."""
    try:
        print("➡️ Fetching data from URL...")
        response = requests.get(url)
        response.raise_for_status()
        print("✅ Data fetched successfully!")
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching data: {e}")
        return None

def infer_column_types(rows):
    """Infers data types (INTEGER, REAL, TEXT) for each column, ignoring empty column names."""
    if not rows:
        return {}
        
    column_types = {}
    # Filter out any column names that are empty strings
    columns = [col for col in rows[0].keys() if col]
    
    for col in columns:
        is_integer = True
        is_real = True
        
        for row in rows:
            value = str(row.get(col, ''))
            if value is None or value == '':
                continue # Skip empty values in type detection

            # Check for INTEGER
            if is_integer and not (value.isdigit() or (value.startswith('-') and value[1:].isdigit())):
                is_integer = False

            # Check for REAL (if not an integer)
            if is_real and not is_integer:
                try:
                    float(value)
                except ValueError:
                    is_real = False
            
            # If it's not a number, it must be TEXT
            if not is_integer and not is_real:
                break # Optimization: once it's TEXT, it stays TEXT
        
        if is_integer:
            column_types[col] = "INTEGER"
        elif is_real:
            column_types[col] = "REAL"
        else:
            column_types[col] = "TEXT"
            
    return column_types

def write_to_sqlite(data, db_name='database.db'):
    """
    Writes the fetched data into an SQLite database with inferred types, 
    ignoring any columns with empty string names.
    
    SQLite does not have a storage class set aside for storing dates and/or times. 
    Instead, the built-in Date And Time Functions of SQLite are capable of 
    storing dates and times as TEXT, REAL, or INTEGER values:

    TEXT as ISO8601 strings ("YYYY-MM-DD HH:MM:SS.SSS").
    REAL as Julian day numbers.
    INTEGER as Unix Time, the number of seconds since 1970-01-01 00:00:00 UTC.
    """
    if not data:
        print("No data to write.")
        return

    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    print(f"✅ Connected to SQLite database '{db_name}'")

    for table_name, rows in data.items():
        if not rows:
            print(f"⚠️ Skipping empty sheet: {table_name}")
            continue

        # Filter out any column names that are empty strings
        columns = [col for col in rows[0].keys() if col]

        # If after filtering there are no columns, skip this table
        if not columns:
            print(f"⚠️ Skipping table '{table_name}' as it has no valid column headers.")
            continue

        sanitized_table_name = "".join(c for c in table_name if c.isalnum())
        
        # Infer data types for this table
        column_types = infer_column_types(rows)
        print(f"Inferred types for '{sanitized_table_name}': {column_types}")

        # Create the table with correct types and quoted names
        column_definitions = ", ".join([f'"{col}" {col_type}' for col, col_type in column_types.items()])
        
        # Drop table to ensure schema is updated
        cursor.execute(f"DROP TABLE IF EXISTS {sanitized_table_name}")
        create_table_sql = f"CREATE TABLE {sanitized_table_name} ({column_definitions})"
        cursor.execute(create_table_sql)
        print(f"Table '{sanitized_table_name}' created.")

        # Prepare and execute the insert statements
        placeholders = ", ".join(["?"] * len(columns))
        quoted_columns = ", ".join(f'"{c}"' for c in columns)
        insert_sql = f"INSERT INTO {sanitized_table_name} ({quoted_columns}) VALUES ({placeholders})"
        
        # Extract only the values for the valid columns
        values_to_insert = [tuple(row.get(col, None) for col in columns) for row in rows]
        
        cursor.executemany(insert_sql, values_to_insert)
        print(f"Inserted {len(values_to_insert)} rows into '{sanitized_table_name}'.")

    conn.commit()
    conn.close()
    print("✅ Database write complete and connection closed.")

def sync_database():
    """The main function to orchestrate the fetching and writing process."""
    APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL")
    
    if not APPS_SCRIPT_URL:
        print("❌ APPS_SCRIPT_URL not found in environment variables.")
        return
        
    print("🚀 Starting database sync process...")
    sheet_data = fetch_data_from_sheet(APPS_SCRIPT_URL)
    
    if sheet_data:
        write_to_sqlite(sheet_data, 'sheets.db')
    print("🏁 Database sync process finished.")


if __name__ == "__main__":
    sync_database()