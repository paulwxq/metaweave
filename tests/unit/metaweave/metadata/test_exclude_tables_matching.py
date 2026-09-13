from unittest.mock import MagicMock, patch

from metaweave.core.metadata.models import DatabaseObjectRef


class TestExcludeTablesMatching:
    @patch("metaweave.core.metadata.generator.MetadataGenerator._init_components")
    @patch("metaweave.core.metadata.generator.MetadataGenerator._load_config")
    def test_plain_table_name_matches_all_schemas(self, mock_load_config, mock_init_components):
        from metaweave.core.metadata.generator import MetadataGenerator

        mock_load_config.return_value = {
            "database": {
                "exclude_tables": ["orders"],
            }
        }

        generator = MetadataGenerator("configs/metadata_config.yaml")
        generator.active_step = "ddl"
        generator.connector = MagicMock()
        generator.connector.get_database_objects.side_effect = [
            [
                DatabaseObjectRef("public", "orders", "table"),
                DatabaseObjectRef("public", "customers", "table"),
            ],
            [
                DatabaseObjectRef("ods", "orders", "table"),
                DatabaseObjectRef("ods", "payments", "table"),
            ],
        ]

        tables = generator._get_tables_to_process(["public", "ods"], None)

        assert tables == [
            ("public", "customers", "table"),
            ("ods", "payments", "table"),
        ]

    @patch("metaweave.core.metadata.generator.MetadataGenerator._init_components")
    @patch("metaweave.core.metadata.generator.MetadataGenerator._load_config")
    def test_schema_table_only_matches_specific_schema(self, mock_load_config, mock_init_components):
        from metaweave.core.metadata.generator import MetadataGenerator

        mock_load_config.return_value = {
            "database": {
                "exclude_tables": ["public.orders"],
            }
        }

        generator = MetadataGenerator("configs/metadata_config.yaml")
        generator.active_step = "ddl"
        generator.connector = MagicMock()
        generator.connector.get_database_objects.side_effect = [
            [
                DatabaseObjectRef("public", "orders", "table"),
                DatabaseObjectRef("public", "customers", "table"),
            ],
            [
                DatabaseObjectRef("ods", "orders", "table"),
                DatabaseObjectRef("ods", "payments", "table"),
            ],
        ]

        tables = generator._get_tables_to_process(["public", "ods"], None)

        assert tables == [
            ("public", "customers", "table"),
            ("ods", "orders", "table"),
            ("ods", "payments", "table"),
        ]

    @patch("metaweave.core.metadata.generator.MetadataGenerator._init_components")
    @patch("metaweave.core.metadata.generator.MetadataGenerator._load_config")
    def test_schema_star_matches_all_tables_in_schema(self, mock_load_config, mock_init_components):
        from metaweave.core.metadata.generator import MetadataGenerator

        mock_load_config.return_value = {
            "database": {
                "exclude_tables": ["public.*"],
            }
        }

        generator = MetadataGenerator("configs/metadata_config.yaml")
        generator.active_step = "ddl"
        generator.connector = MagicMock()
        generator.connector.get_database_objects.side_effect = [
            [
                DatabaseObjectRef("public", "orders", "table"),
                DatabaseObjectRef("public", "customers", "table"),
            ],
            [
                DatabaseObjectRef("ods", "orders", "table"),
                DatabaseObjectRef("ods", "payments", "table"),
            ],
        ]

        tables = generator._get_tables_to_process(["public", "ods"], None)

        assert tables == [
            ("ods", "orders", "table"),
            ("ods", "payments", "table"),
        ]

    @patch("metaweave.core.metadata.generator.MetadataGenerator._init_components")
    @patch("metaweave.core.metadata.generator.MetadataGenerator._load_config")
    def test_schema_prefix_matches_only_specific_schema(self, mock_load_config, mock_init_components):
        from metaweave.core.metadata.generator import MetadataGenerator

        mock_load_config.return_value = {
            "database": {
                "exclude_tables": ["public.order*"],
            }
        }

        generator = MetadataGenerator("configs/metadata_config.yaml")
        generator.active_step = "ddl"
        generator.connector = MagicMock()
        generator.connector.get_database_objects.side_effect = [
            [
                DatabaseObjectRef("public", "orders", "table"),
                DatabaseObjectRef("public", "order_items", "table"),
                DatabaseObjectRef("public", "customers", "table"),
            ],
            [
                DatabaseObjectRef("ods", "orders", "table"),
                DatabaseObjectRef("ods", "order_items", "table"),
                DatabaseObjectRef("ods", "payments", "table"),
            ],
        ]

        tables = generator._get_tables_to_process(["public", "ods"], None)

        assert tables == [
            ("public", "customers", "table"),
            ("ods", "orders", "table"),
            ("ods", "order_items", "table"),
            ("ods", "payments", "table"),
        ]

    @patch("metaweave.core.metadata.generator.MetadataGenerator._init_components")
    @patch("metaweave.core.metadata.generator.MetadataGenerator._load_config")
    def test_unsupported_three_part_pattern_is_ignored(self, mock_load_config, mock_init_components, caplog):
        from metaweave.core.metadata.generator import MetadataGenerator

        mock_load_config.return_value = {
            "database": {
                "exclude_tables": ["highway_db.public.orders"],
            }
        }

        generator = MetadataGenerator("configs/metadata_config.yaml")
        generator.active_step = "ddl"
        generator.connector = MagicMock()
        generator.connector.get_database_objects.return_value = [
            DatabaseObjectRef("public", "orders", "table"),
            DatabaseObjectRef("public", "customers", "table"),
        ]

        tables = generator._get_tables_to_process(["public"], None)

        assert tables == [
            ("public", "orders", "table"),
            ("public", "customers", "table"),
        ]
        assert "暂不支持三段式或多段模式" in caplog.text
