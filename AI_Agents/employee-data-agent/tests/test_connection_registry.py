import unittest

from agent.connection_registry import ConnectionRegistry


class ConnectionRegistryTests(unittest.TestCase):

    def test_catalog_connection_is_registered_read_only_postgres(self):
        registry = ConnectionRegistry().load()
        definition = registry._definitions["hr_postgres_readonly"]

        self.assertEqual(definition.dialect, "postgres")
        self.assertEqual(definition.database_name, "hr_database")
        self.assertTrue(definition.read_only)

    def test_sql_server_connection_is_registered(self):
        registry = ConnectionRegistry().load()
        definition = registry._definitions["hr_sqlserver_readonly"]

        self.assertEqual(definition.dialect, "sqlserver")
        self.assertTrue(definition.read_only)


if __name__ == "__main__":
    unittest.main()