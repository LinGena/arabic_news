import json
import traceback
from typing import Any, NoReturn, Dict
import os
import psycopg2


class PostgreSQL:
    def __init__(self):
        self.connection = psycopg2.connect(dbname=os.getenv("POSTGRES_DB_NAME"), user=os.getenv("POSTGRES_USER"),
                                           password=os.getenv("POSTGRES_PASSWORD"), host=os.getenv("HOST"))

    def __del__(self):
        try:
            self.close_connection()
        except AttributeError:
            pass

    def execute_query_with_results(self, query: str, values: list | None = None) -> list:
        cursor = self.connection.cursor()
        try:
            if values:
                values = [json.dumps(v, default=str) if isinstance(v, dict) else v for v in values]
                cursor.execute(query, values)
            else:
                cursor.execute(query)
            column_names = [desc[0] for desc in cursor.description]
            rows = []
            for row in cursor.fetchall():
                row_dict = dict(zip(column_names, row))
                rows.append(row_dict)
            self.connection.commit()
            cursor.close()
            return rows
        except psycopg2.Error as e:
            print(query, values)
            cursor.execute('rollback')
            cursor.close()
            print(f"Error executing query with results: {e}")
            print(traceback.format_exc())

    def close_connection(self):
        self.connection.close()


class PostgreSQLTable:
    def __init__(self, table_name):
        self.table_name = table_name
        self.db = PostgreSQL()

    def insert_row(self, data: dict) -> dict | None:
        try:
            column_names = ", ".join(data.keys())
            values = list(data.values())
            placeholders = ", ".join(["%s"] * len(values))
            query = f"INSERT INTO {self.table_name} ({column_names}) VALUES ({placeholders}) RETURNING *"
            inserted_row = self.db.execute_query_with_results(query, values)
            self.db.connection.commit()
            if inserted_row:
                return inserted_row[0]
            else:
                return None
        except Exception as ex:
            print(ex)

    def update_row(self, custom_field: str, custom_value: Any, data: dict) -> dict | None:
        try:
            set_columns = ", ".join([f"{column} = %s" for column in data.keys()])
            set_values = list(data.values())
            condition = f"{custom_field} = %s"
            condition_value = [custom_value]
            query = f"UPDATE {self.table_name} SET {set_columns} WHERE {condition} RETURNING *"
            updated_row = self.db.execute_query_with_results(query, set_values + condition_value)
            self.db.connection.commit()
            if updated_row:
                return updated_row[0]
            else:
                return None
        except Exception:
            print(traceback.format_exc())

    def delete_row(self, condition_field: str, condition_value: Any) -> None:
        try:
            query = f"DELETE FROM {self.table_name} WHERE {condition_field} = %s RETURNING *"
            self.db.execute_query_with_results(query, [condition_value])
            self.db.connection.commit()
        except Exception:
            print(traceback.format_exc())

    def get_all_rows(self) -> list | NoReturn:
        cursor = self.db.connection.cursor()
        try:
            query = f"SELECT * FROM {self.table_name} order by id"
            cursor.execute(query)
            column_names = [desc[0] for desc in cursor.description]
            rows = []
            for row in cursor.fetchall():
                row_dict = dict(zip(column_names, row))
                rows.append(row_dict)
            cursor.close()
            self.db.connection.commit()
            return rows
        except Exception:
            cursor.execute('rollback')
            print(traceback.format_exc())

    def get_row(self, conditions: Dict[str, Any]) -> dict | None:
        cursor = self.db.connection.cursor()
        try:
            where_clause = " AND ".join([f"{field} = %s" for field in conditions.keys()])
            query = f"SELECT * FROM {self.table_name} WHERE {where_clause}"
            cursor.execute(query, tuple(conditions.values()))
            results = cursor.fetchall()
            cursor.close()
            if results:
                row_data = results[0]
                column_names = [desc[0] for desc in cursor.description]
                row_dict = {column: value for column, value in zip(column_names, row_data)}
                return row_dict
            else:
                return None
        except Exception:
            cursor.execute('rollback')
            print(traceback.format_exc())
        finally:
            cursor.close()

    def get_rows_with_filter(self, condition_field: str, condition_value: Any) -> list | NoReturn:
        cursor = self.db.connection.cursor()
        try:
            query = f"SELECT * FROM {self.table_name} WHERE {condition_field} = %s"
            cursor.execute(query, (condition_value,))
            column_names = [desc[0] for desc in cursor.description]
            rows = []
            for row in cursor.fetchall():
                row_dict = dict(zip(column_names, row))
                rows.append(row_dict)
            cursor.close()
            self.db.connection.commit()
            return rows
        except Exception:
            cursor.execute('rollback')
            print(traceback.format_exc())

    def check_table(self) -> bool:
        cursor = self.db.connection.cursor()
        sql = "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)"
        cursor.execute(sql, (self.table_name,))
        res = cursor.fetchone()
        return res[0] if res else False
    
    def bulk_insert_or_update(self, data_list: list[dict]) -> None:
        if not data_list:
            print("Empty data list for bulk insert or update.")
            return
        cursor = self.db.connection.cursor()
        try:
            columns = data_list[0].keys()
            column_names = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            values = [tuple(item[column] for column in columns) for item in data_list]
            query = f"""
                INSERT INTO {self.table_name} ({column_names})
                VALUES ({placeholders})
                ON CONFLICT DO NOTHING
                """
            cursor.executemany(query, values)
            self.db.connection.commit()
            print(f"Inserted {cursor.rowcount} rows into {self.table_name} (skipped duplicates).")
        except Exception as e:
            cursor.execute("ROLLBACK")
            print(f"Error during bulk insert or update: {e}")
            print(traceback.format_exc())
        finally:
            cursor.close()