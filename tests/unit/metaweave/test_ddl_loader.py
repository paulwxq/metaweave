import textwrap

from metaweave.core.metadata.ddl_loader import DDLLoader


def _write_sample_ddl(tmp_path):
    ddl_text = textwrap.dedent(
        """
        CREATE TABLE IF NOT EXISTS public.dim_company (
            company_id INTEGER NOT NULL,
            company_name CHARACTER VARYING(200) NOT NULL,
            region_id INTEGER,
            CONSTRAINT pk_dim_company PRIMARY KEY (company_id),
            CONSTRAINT fk_company_region FOREIGN KEY (region_id) REFERENCES public.dim_region(region_id)
        );

        COMMENT ON COLUMN public.dim_company.company_id IS '公司ID';
        COMMENT ON COLUMN public.dim_company.company_name IS '公司名称';
        COMMENT ON TABLE public.dim_company IS '公司维表';

        CREATE INDEX idx_company_name ON public.dim_company(company_name);

        /* SAMPLE_RECORDS
        {
          "version": 1,
          "table": "public.dim_company",
          "generated_at": "2025-11-20T03:39:21.662152Z",
          "records": [
            {"label": "Record 1", "data": {"company_id": "1", "company_name": "A"}},
            {"label": "Record 2", "data": {"company_id": "2", "company_name": "B"}},
            {"label": "Record 3", "data": {"company_id": "3", "company_name": "C"}}
          ]
        }
        */
        """
    ).strip()
    ddl_file = tmp_path / "postgres.public.dim_company.sql"
    ddl_file.write_text(ddl_text, encoding="utf-8")
    return ddl_file


def test_ddl_loader_parses_structure_and_samples(tmp_path):
    _write_sample_ddl(tmp_path)

    loader = DDLLoader(tmp_path)
    parsed = loader.load_table("public", "dim_company")
    metadata = parsed.metadata

    assert metadata.schema_name == "public"
    assert metadata.table_name == "dim_company"
    assert metadata.comment == "公司维表"
    assert len(metadata.columns) == 3
    assert metadata.columns[0].column_name == "company_id"
    assert metadata.columns[0].comment == "公司ID"
    assert metadata.primary_keys[0].columns == ["company_id"]
    assert metadata.foreign_keys[0].target_table == "dim_region"
    assert metadata.indexes[0].index_name == "idx_company_name"
    assert metadata.sample_records == [
        {"company_id": "1", "company_name": "A"},
        {"company_id": "2", "company_name": "B"},
        {"company_id": "3", "company_name": "C"},
    ]


def test_ddl_loader_parses_compact_sampled_records(tmp_path):
    ddl_file = tmp_path / "postgres.public.events.sql"
    ddl_file.write_text(
        textwrap.dedent(
            """
            CREATE TABLE IF NOT EXISTS public.events (
                event_id INTEGER,
                event_name TEXT
            );

            /* SAMPLED_RECORDS
            {
              "object_type": "table",
              "object_name": "public.events",
              "records": [
                {"event_id": "1", "event_name": "created"},
                {"event_id": "2", "event_name": "completed"}
              ]
            }
            */
            """
        ).strip(),
        encoding="utf-8",
    )

    parsed = DDLLoader(tmp_path).load_table("public", "events")

    assert parsed.sample_records == [
        {"event_id": "1", "event_name": "created"},
        {"event_id": "2", "event_name": "completed"},
    ]


def test_ddl_loader_parses_postgres_index_features(tmp_path):
    ddl_file = tmp_path / "postgres.public.accounts.sql"
    ddl_file.write_text(
        textwrap.dedent(
            """
            CREATE TABLE public.accounts (
                account_id INTEGER,
                email TEXT,
                created_at TIMESTAMP,
                deleted_at TIMESTAMP
            );

            CREATE UNIQUE INDEX accounts_email_uidx
            ON public.accounts USING btree (account_id, lower(email))
            INCLUDE (created_at)
            WHERE deleted_at IS NULL;
            """
        ).strip(),
        encoding="utf-8",
    )

    parsed = DDLLoader(tmp_path).load_table("public", "accounts")

    assert len(parsed.metadata.indexes) == 1
    index = parsed.metadata.indexes[0]
    assert index.index_name == "accounts_email_uidx"
    assert index.index_type == "btree"
    assert index.is_unique is True
    assert index.columns == ["account_id"]
    assert index.key_expressions == ["account_id", "lower(email)"]
    assert index.included_columns == ["created_at"]
    assert index.condition == "deleted_at IS NULL"
    assert index.is_constraint_backed is False
    assert index.definition.startswith("CREATE UNIQUE INDEX")


def test_ddl_loader_keeps_commas_inside_index_expressions(tmp_path):
    ddl_file = tmp_path / "postgres.public.events.sql"
    ddl_file.write_text(
        textwrap.dedent(
            """
            CREATE TABLE public.events (
                event_id INTEGER,
                event_code TEXT
            );

            CREATE INDEX events_code_idx ON public.events
            USING hash (concat(event_code, ',', event_id));
            """
        ).strip(),
        encoding="utf-8",
    )

    parsed = DDLLoader(tmp_path).load_table("public", "events")

    index = parsed.metadata.indexes[0]
    assert index.index_type == "hash"
    assert index.columns == []
    assert index.key_expressions == ["concat(event_code, ',', event_id)"]
