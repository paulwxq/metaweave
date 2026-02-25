# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Communication Language

**始终使用简体中文与用户交流。** Always communicate with the user in Simplified Chinese.

## Project Overview

MetaWeave is a database metadata generation and enhancement platform that extracts metadata from PostgreSQL databases, generates data profiles, discovers table relationships, and exports to graph databases (Neo4j) and vector databases (Milvus). The project supports both traditional rule-based analysis and LLM-enhanced semantic understanding.

## Common Commands

### Virtual Environment Setup

项目根目录下有两套虚拟环境，按运行平台选择：

| 目录 | 适用平台 | 激活命令 |
|------|---------|---------|
| `.venv-wsl` | WSL / Linux | `source .venv-wsl/bin/activate` |
| `.venv-win` | Windows（PowerShell）| `.venv-win\Scripts\Activate.ps1` |
| `.venv-win` | Windows（CMD）| `.venv-win\Scripts\activate.bat` |

**创建环境并同步依赖（WSL）**：
```bash
uv venv .venv-wsl --python 3.12
source .venv-wsl/bin/activate
uv sync --active
```

**创建环境并同步依赖（Windows）**：
```powershell
uv venv .venv-win --python 3.12
.venv-win\Scripts\Activate.ps1
uv sync --active
```

> 两套环境完全独立，不可混用。在 WSL 下运行测试必须激活 `.venv-wsl`，在 Windows 下必须激活 `.venv-win`。

```bash
# Install in editable mode（激活环境后执行）
uv pip install -e .
```

### Running MetaWeave

```bash
# Show help
uv run metaweave --help

# Generate metadata for all tables
uv run metaweave metadata --config configs/metadata_config.yaml

# Generate specific step (ddl, json, json_llm, rel, rel_llm, cql, cql_llm, md)
uv run metaweave metadata --config configs/metadata_config.yaml --step ddl

# Filter by schema or tables
uv run metaweave metadata -c configs/metadata_config.yaml --schemas public
uv run metaweave metadata -c configs/metadata_config.yaml --tables users,orders

# Adjust concurrency
uv run metaweave metadata -c configs/metadata_config.yaml --max-workers 8

# Enable debug mode
uv run metaweave --debug metadata -c configs/metadata_config.yaml
```

### Testing

运行测试前需先激活对应平台的虚拟环境（见上方 Virtual Environment Setup）。

```bash
# 激活环境后运行全部测试
pytest tests/

# 运行指定目录
pytest tests/metaweave_relationships/

# 带覆盖率
pytest --cov=metaweave tests/

# 运行单个文件
pytest tests/test_composite_matching.py
```

### Development Tools

```bash
# Format code with black
black metaweave/

# Lint with ruff
ruff check metaweave/
```

## Architecture

### Processing Pipeline

MetaWeave uses a multi-step pipeline with two parallel tracks:

**Standard Track (Rule-based)**:
1. `ddl` - Extract table structures from DB → `output/ddl/*.sql`
2. `json` - Generate data profiles from DDL + DB sampling → `output/json/*.json`
3. `rel` - Discover relationships using algorithms + DB sampling → `output/rel/*.json`
4. `cql` - Generate Neo4j CQL scripts (file-only, no DB access) → `output/cql/*.cypher`

**LLM-Enhanced Track**:
1. `ddl` - Same as standard track
2. `json_llm` - LLM-enhanced profiles with semantic understanding → `output/json_llm/*.json`
3. `rel_llm` - LLM-inferred relationships + DB validation → `output/rel/*.json`
4. `cql_llm` - Generate CQL from LLM-enhanced data → `output/cql/*.cypher`

**Independent**:
- `md` - Generate Markdown documentation directly from DB

### Database Access Requirements

**Critical**: All steps except `cql` and `cql_llm` require database access, even when reading from files:
- `ddl` - Queries table structures, constraints, indexes
- `json` - Executes COUNT queries and samples data for statistics
- `json_llm` - Extracts metadata and samples data (DDL only checked for directory existence)
- `rel` - Samples data for relationship scoring (inclusion rate, Jaccard index)
- `rel_llm` - Same sampling as `rel` for validation
- `md` - Direct queries for structure and samples

### Core Modules

**`metaweave/core/metadata/`** - Metadata extraction and generation
- `generator.py` - Main orchestrator for metadata generation
- `extractor.py` - Extracts metadata from PostgreSQL information_schema
- `connector.py` - Database connection and query execution
- `comment_generator.py` - LLM-based comment generation with caching
- `logical_key_detector.py` - Identifies candidate logical primary keys
- `formatter.py` - Exports to DDL, JSON, Markdown formats
- `llm_json_generator.py` - LLM-enhanced JSON generation
- `models.py` - Data structures (TableMetadata, ColumnInfo, etc.)

**`metaweave/core/relationships/`** - Table relationship discovery
- `pipeline.py` - Orchestrates relationship discovery process
- `candidate_generator.py` - Generates candidate relationships based on naming patterns
- `scorer.py` - Scores candidates using DB sampling (inclusion rate, Jaccard, etc.)
- `llm_relationship_discovery.py` - LLM-based semantic relationship inference
- `models.py` - Relation data structures

**`metaweave/core/cql_generator/`** - Neo4j CQL generation
- `generator.py` - Generates Cypher scripts from JSON + relationship data
- `reader.py` - Reads JSON metadata files
- `writer.py` - Writes CQL output files

**`metaweave/core/loaders/`** - Data loaders for Neo4j/Milvus
- `factory.py` - Factory pattern for loader creation
- `cql_loader.py` - Loads CQL into Neo4j
- `table_schema_loader.py` - Loads table schemas into vector DB
- `dim_value_loader.py` - Loads dimension values

**`metaweave/services/`** - Shared services
- `llm_service.py` - LLM integration (qwen-plus, deepseek) via LangChain
- `embedding_service.py` - Text embedding for vector search
- `vector_db/` - Vector database adapters (Milvus, pgvector)

**`metaweave/cli/`** - Command-line interface
- `main.py` - Main CLI entry point with subcommands
- `metadata_cli.py` - Metadata generation commands
- `loader_cli.py` - Data loading commands
- `dim_config_cli.py` - Dimension configuration commands

### Configuration

Primary config file: `configs/metadata_config.yaml`

Key sections:
- `database` - PostgreSQL connection, schemas, exclusions
- `llm` - Provider selection (qwen-plus/deepseek), API keys, model parameters
- `llm_comment_generation` - Enable/disable LLM comments, language
- `logical_key_detection` - Candidate key discovery settings
- `sampling` - Sample size for data profiling
- `output` - Output directories and formats

Environment variables (`.env`):
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `DASHSCOPE_API_KEY`, `DASHSCOPE_MODEL` (for qwen-plus)
- `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_API_BASE` (for deepseek)

### Data Models

**TableMetadata** - Complete table information including columns, constraints, indexes, sample data

**ColumnInfo** - Column details with optional statistics and LLM-generated comments

**Relation** - Table relationships (single or composite columns) with:
- `relationship_type`: "foreign_key" or "inferred"
- `cardinality`: "1:1", "1:N", "N:1", "M:N"
- `composite_score`: 0-1 confidence for inferred relationships
- `score_details`: Breakdown by inclusion_rate, name_similarity, type_compatibility, jaccard_index

### LLM Integration

LLM calls are used for:
1. **Comment Generation** (`comment_generator.py`) - Generates missing table/column descriptions
2. **Semantic Classification** (`json_llm` step) - Infers table categories and business domains
3. **Relationship Inference** (`rel_llm` step) - Discovers implicit relationships through semantic analysis

LLM outputs are written into the generated artifacts (DDL/JSON). There is no local comment cache file.

### Output Structure

```
output/
├── ddl/              # PostgreSQL DDL with comments and sample data annotations
├── json/             # Rule-based table/column profiles
├── json_llm/         # LLM-enhanced profiles (simplified schema)
├── rel/              # Discovered relationships (relationships_global.json)
├── cql/              # Neo4j Cypher import scripts
└── md/               # Human-readable Markdown documentation
```

## Development Notes

### Project Origin
This is a standalone project migrated from `nl2sql_v3/src/metaweave/` (copy only, no modifications to original).

### Virtual Environment
项目使用 `uv` 管理依赖。`.venv-wsl` 用于 WSL/Linux，`.venv-win` 用于 Windows，两套环境独立维护，不可混用。依赖同步方式见上方 Virtual Environment Setup。

### Concurrent Processing
The metadata generator supports concurrent table processing via `--max-workers` flag. Default is 4 workers.

### Logging
- Log files: `logs/metaweave/*.log`
- Logging config: `configs/logging.yaml`
- Use `--debug` flag for verbose output

### Testing Structure
- `tests/unit/` - Unit tests for individual components
- `tests/metaweave_relationships/` - Relationship discovery integration tests
- `test_composite_matching.py` - Composite key matching tests
- `test_two_stage_matching.py` - Two-stage matching algorithm tests

### Code Organization
- The package includes both `metaweave/` and `services/` modules
- Use `python -m metaweave.cli.main` or `uv run metaweave` to invoke CLI
- Scripts in `scripts/` provide alternative entry points for specific operations
