import os
from pathlib import Path

from dotenv import load_dotenv
from mssql_python import connect


# ------------------------------------------------------------------
# Load environment variables
# ------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / "backend" / ".env"

if not ENV_FILE.exists():
    raise FileNotFoundError(f".env file not found: {ENV_FILE}")

load_dotenv(ENV_FILE)

connection_string = os.environ.get("AZURE_SQL_CONNECTIONSTRING")

if not connection_string:
    raise RuntimeError(
        "AZURE_SQL_CONNECTIONSTRING is not defined in backend/.env"
    )


# ------------------------------------------------------------------
# Pretty output helpers
# ------------------------------------------------------------------

def section(title: str):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def success(message: str):
    print(f"[PASS] {message}")


def failure(message: str):
    print(f"[FAIL] {message}")


# ------------------------------------------------------------------
# Azure SQL tests
# ------------------------------------------------------------------

def main():
    section("1. Azure SQL Connection")

    try:
        conn = connect(
            connection_string,
            timeout=30,
        )
    except Exception as exc:
        failure("Unable to connect to Azure SQL.")
        raise exc

    try:
        success("Connection established.")

        cursor = conn.cursor()

        # ----------------------------------------------------------
        # Test 1: basic connection / identity
        # ----------------------------------------------------------

        cursor.execute(
            """
            SELECT
                DB_NAME() AS database_name,
                SUSER_SNAME() AS login_name,
                SYSUTCDATETIME() AS database_time;
            """
        )

        row = cursor.fetchone()

        print(f"Database : {row[0]}")
        print(f"Login    : {row[1]}")
        print(f"DB time  : {row[2]}")

        success("Basic SQL query executed successfully.")

        # ----------------------------------------------------------
        # Test 2: database edition / service objective
        # ----------------------------------------------------------

        section("2. Database Information")

        cursor.execute(
            """
            SELECT
                DATABASEPROPERTYEX(
                    DB_NAME(),
                    'Edition'
                ) AS edition,
                DATABASEPROPERTYEX(
                    DB_NAME(),
                    'ServiceObjective'
                ) AS service_objective;
            """
        )

        row = cursor.fetchone()

        print(f"Edition           : {row[0]}")
        print(f"Service objective : {row[1]}")

        success("Database information retrieved.")

        # ----------------------------------------------------------
        # Test 3: native VECTOR support
        # ----------------------------------------------------------

        section("3. Native Vector Support")

        vector_supported = False

        try:
            cursor.execute(
                """
                SELECT
                    CAST(
                        '[0.1, 0.2, 0.3]'
                        AS VECTOR(3)
                    ) AS test_vector;
                """
            )

            row = cursor.fetchone()

            print(f"Test vector : {row[0]}")

            vector_supported = True
            success("Azure SQL native VECTOR type is supported.")

        except Exception as exc:
            failure("Native VECTOR test failed.")
            print(f"Reason: {exc}")

        # ----------------------------------------------------------
        # Test 4: CREATE / INSERT / SELECT / DROP permissions
        # ----------------------------------------------------------

        section("4. Database Write Permissions")

        test_table = "dbo._connection_test"

        try:
            # Clean up a table left over from an interrupted test.
            cursor.execute(
                """
                IF OBJECT_ID(
                    'dbo._connection_test',
                    'U'
                ) IS NOT NULL
                    DROP TABLE dbo._connection_test;
                """
            )

            conn.commit()

            # CREATE
            cursor.execute(
                """
                CREATE TABLE dbo._connection_test
                (
                    id INT NOT NULL PRIMARY KEY,
                    message NVARCHAR(100) NOT NULL
                );
                """
            )

            conn.commit()

            success("CREATE TABLE permission works.")

            # INSERT
            cursor.execute(
                """
                INSERT INTO dbo._connection_test
                    (id, message)
                VALUES
                    (1, 'Azure SQL connection works');
                """
            )

            conn.commit()

            success("INSERT permission works.")

            # SELECT
            cursor.execute(
                """
                SELECT
                    id,
                    message
                FROM dbo._connection_test;
                """
            )

            row = cursor.fetchone()

            print(f"Test row : {row[0]} | {row[1]}")

            success("SELECT permission works.")

            # DROP
            cursor.execute(
                """
                DROP TABLE dbo._connection_test;
                """
            )

            conn.commit()

            success("DROP TABLE permission works.")

        except Exception as exc:
            failure("Database write-permission test failed.")
            print(f"Reason: {exc}")

            # Try not to leave our test table behind.
            try:
                cursor.execute(
                    """
                    IF OBJECT_ID(
                        'dbo._connection_test',
                        'U'
                    ) IS NOT NULL
                        DROP TABLE dbo._connection_test;
                    """
                )
                conn.commit()
            except Exception:
                pass

        # ----------------------------------------------------------
        # Summary
        # ----------------------------------------------------------

        section("5. Readiness Summary")

        success("Azure SQL connection")
        success("SQL authentication")
        success("SQL query execution")

        if vector_supported:
            success("Native VECTOR support")
        else:
            failure("Native VECTOR support")

        print()
        print("Azure SQL readiness test complete.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()