import unittest
from unittest.mock import MagicMock, patch

import psycopg

from app import database


class DatabaseBootstrapTest(unittest.TestCase):
    @patch("app.database.psycopg.connect")
    def test_existing_database_needs_no_maintenance_connection(self, connect):
        target_connection = MagicMock()
        connect.return_value = target_connection

        database.ensure_database_exists()

        connect.assert_called_once_with(database.DATABASE_URL)
        target_connection.close.assert_called_once_with()

    @patch("app.database.psycopg.connect")
    def test_missing_database_is_created_from_maintenance_database(self, connect):
        target_database = database.conninfo_to_dict(database.DATABASE_URL)["dbname"]
        maintenance_connection = MagicMock()
        maintenance_connection.__enter__.return_value = maintenance_connection
        maintenance_connection.execute.return_value.fetchone.return_value = None
        connect.side_effect = [
            psycopg.errors.InvalidCatalogName("database does not exist"),
            maintenance_connection,
        ]

        database.ensure_database_exists()

        self.assertEqual(connect.call_count, 2)
        maintenance_connection.execute.assert_any_call(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (target_database,),
        )
        create_call = maintenance_connection.execute.call_args_list[-1]
        self.assertIn("CREATE DATABASE", create_call.args[0].as_string(None))


if __name__ == "__main__":
    unittest.main()
