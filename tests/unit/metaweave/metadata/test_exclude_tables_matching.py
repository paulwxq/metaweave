from unittest.mock import MagicMock, patch


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
        generator.connector.get_tables.side_effect = [
            ["orders", "customers"],
            ["orders", "payments"],
        ]

        tables = generator._get_tables_to_process(["public", "ods"], None)

        assert tables == [("public", "customers"), ("ods", "payments")]

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
        generator.connector.get_tables.side_effect = [
            ["orders", "customers"],
            ["orders", "payments"],
        ]

        tables = generator._get_tables_to_process(["public", "ods"], None)

        assert tables == [("public", "customers"), ("ods", "orders"), ("ods", "payments")]

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
        generator.connector.get_tables.side_effect = [
            ["orders", "customers"],
            ["orders", "payments"],
        ]

        tables = generator._get_tables_to_process(["public", "ods"], None)

        assert tables == [("ods", "orders"), ("ods", "payments")]

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
        generator.connector.get_tables.side_effect = [
            ["orders", "order_items", "customers"],
            ["orders", "order_items", "payments"],
        ]

        tables = generator._get_tables_to_process(["public", "ods"], None)

        assert tables == [
            ("public", "customers"),
            ("ods", "orders"),
            ("ods", "order_items"),
            ("ods", "payments"),
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
        generator.connector.get_tables.return_value = ["orders", "customers"]

        tables = generator._get_tables_to_process(["public"], None)

        assert tables == [("public", "orders"), ("public", "customers")]
        assert "暂不支持三段式或多段模式" in caplog.text
