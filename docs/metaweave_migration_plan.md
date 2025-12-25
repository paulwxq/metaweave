# MetaWeave 模块迁移规划文档（Copy-only）

## 文档信息

- 文档版本：v1.1（根据讨论修订：`metaweave.*` + `metaweave/services` + 扁平化 `configs/` & `output/`）
- 创建日期：2025-12-23
- 修订日期：2025-12-24
- 迁移类型：复制（Copy），**不移动**、**不修改** `nl2sql_v3/` 下任何文件
- 源项目：`nl2sql_v3/`
- 目标目录：与 `nl2sql_v3/` 平级的 `metaweave/`（新建）

---

## 0. 迁移目标与边界

### 0.1 迁移目标

将 `nl2sql_v3/src/metaweave/` 从“NL2SQL 子模块”迁移为**独立项目** `metaweave/`，并完成以下重构口径：

1. Python 导入命名空间从 `src.metaweave.*` 改为 `metaweave.*`
2. 将 MetaWeave 所需的公共能力从 `nl2sql_v3/src/services/...` **复制**到新项目 `metaweave/services/`，并在新项目中改为 `services.*` 导入
3. 扁平化目录：
   - `configs/`：不再使用 `configs/metaweave/...`
   - `output/`：不再使用 `output/metaweave/metadata/...`

### 0.2 迁移原则（强约束）

- **只复制，不 move**：整个过程不对 `nl2sql_v3/` 做任何修改
- **新项目可独立运行**：新项目内部改动只发生在 `metaweave/` 目录
- **安全**：迁移文档/仓库中不得写入真实密码、API Key、Token；`.env` 不入库（只在本机使用）

---

## 1. 需要迁移的内容清单（源外依赖已补齐）

> 说明：以下“需要迁移”均指从 `nl2sql_v3/` 复制到新目录 `metaweave/`。  
> 若后续发现遗漏，以“依赖扫描结果”为准补充（见第 2 节）。

### 1.1 核心代码：MetaWeave 包

- 源：`nl2sql_v3/src/metaweave/`
- 目标：`metaweave/metaweave/`

### 1.2 目录外代码依赖：services 包（复制到项目根 /services）

MetaWeave 代码在 `nl2sql_v3/` 中直接依赖了 `src.services.*`（例如 `ConfigLoader`、Neo4j/PG 连接、Milvus client），因此必须复制到新项目：

- 源：`nl2sql_v3/src/services/`
- 目标：`metaweave/services/`

#### 1.2.1 命名空间说明（避免与 `metaweave.services` 混淆）

新项目会同时存在两类 “services”：

- **业务层 services（MetaWeave 自带）**：路径 `metaweave/metaweave/services/`，导入名 `metaweave.services.*`
- **共享基础设施 services（从 NL2SQL 复制）**：路径 `metaweave/services/`，导入名 `services.*`

两者不会发生 Python 命名冲突（导入根不同），但文档/代码里需要严格区分。

建议最小迁移子集（按当前依赖已验证）：

- `nl2sql_v3/src/services/__init__.py` → `metaweave/services/__init__.py`
- `nl2sql_v3/src/services/config_loader.py` → `metaweave/services/config_loader.py`（在新项目中需修改默认配置路径，见第 3 节）
- `nl2sql_v3/src/services/db/` → `metaweave/services/db/`
  - `neo4j_connection.py`
  - `pg_connection.py`
  - `__init__.py`
- `nl2sql_v3/src/services/vector_db/` → `metaweave/services/vector_db/`
  - `milvus_client.py`
  - `__init__.py`

不建议迁移的子目录（除非后续依赖扫描发现必须）：

- `nl2sql_v3/src/services/langgraph_persistence/`（NL2SQL 特有）
- `nl2sql_v3/src/services/vector_adapter/`（NL2SQL 特有）
- `nl2sql_v3/src/services/embedding/`（NL2SQL 特有；MetaWeave 自带 embedding_service）

#### 1.2.2 `vector_db` “重复/冲突”说明与处理策略

在源项目中确实存在两个相关目录：

- `nl2sql_v3/src/metaweave/services/vector_db/` → 迁移后为 `metaweave/metaweave/services/vector_db/`（导入名：`metaweave.services.vector_db.*`）
  - 作用：MetaWeave 侧的向量库抽象层（`BaseVectorClient`）+ `PgVectorClient` 占位 + `milvus_client.py` 兼容 shim
- `nl2sql_v3/src/services/vector_db/` → 迁移后为 `metaweave/services/vector_db/`（导入名：`services.vector_db.*`）
  - 作用：共享的 **Milvus 低层客户端实现**（`MilvusClient`）

结论：两者**不是重复实现**，而是“上层抽象/兼容层”与“共享实现层”的关系。

新项目建议保留两者，并在新项目中做以下最小改造：

- 将 `metaweave.services.vector_db.milvus_client` 内的 re-export 目标从 `src.services.vector_db.milvus_client` 改为 `services.vector_db.milvus_client`
- 其余 `metaweave.services.vector_db` 文件按需保留（`pgvector_client.py` 目前为占位实现）

### 1.3 配置文件（扁平化到 configs/）

#### 1.3.1 MetaWeave 专用配置

- 源：`nl2sql_v3/configs/metaweave/`
- 目标：`metaweave/configs/`

包含（示例）：

- `metadata_config.yaml`
- `loader_config.yaml`
- `db_domains.yaml`
- `dim_tables.yaml`
- `logging.yaml`
- `.gitkeep`（如需保留空目录语义）

#### 1.3.2 services 所需的全局配置（新增：configs/config.yaml）

`services/config_loader.py` 在 NL2SQL 中默认读取系统级配置文件。由于新项目采用扁平化 `configs/`，需要提供：

- 源：`nl2sql_v3/src/configs/config.yaml`
- 目标：`metaweave/configs/config.yaml`

说明：`nl2sql_v3/configs/` 目录下当前只包含 `configs/metaweave/` 等子目录，并不存在 `nl2sql_v3/configs/config.yaml`；系统级 `config.yaml` 位于 `nl2sql_v3/src/configs/config.yaml`。

该文件至少需要包含 `database:`、`neo4j:`、`vector_database:` 等段（供 `services/db/*` 与 MetaWeave loader 使用）。

### 1.4 脚本

- 源：`nl2sql_v3/scripts/metaweave/`
- 目标：`metaweave/scripts/`

### 1.5 文档

#### 1.5.1 主要设计文档（建议迁移）

- 源：`nl2sql_v3/docs/gen_rag/`
- 目标：`metaweave/docs/design/`

备注：`docs/gen_rag/` 实际文件数可能随提交变化，迁移时以目录实际内容为准。

#### 1.5.2 其他散落文档（可选，但需要评审）

`nl2sql_v3/docs/` 下存在若干 metaweave 相关内容（例如 bugfix 说明、运行命令示例等）。是否迁移建议按如下策略：

- **必须迁移**：直接描述 MetaWeave 的使用/配置/路径且与新项目会冲突的文档
- **可不迁移**：NL2SQL 主项目视角的排障文档（只要不影响新项目可运行）

迁移前先用关键词扫描汇总候选文件（见第 2 节）。

### 1.6 测试（建议迁移到新项目并修正导入/路径）

建议迁移这些目录/文件：

- `nl2sql_v3/tests/unit/metaweave/` → `metaweave/tests/unit/metaweave/`
- `nl2sql_v3/tests/metaweave_relationships/` → `metaweave/tests/metaweave_relationships/`
- 其他顶层 metaweave 相关测试脚本（按实际依赖确认）：
  - `nl2sql_v3/tests/test_two_stage_matching.py`
  - `nl2sql_v3/tests/test_dim_value_search.py`
  - `nl2sql_v3/tests/test_composite_matching.py`
  - `nl2sql_v3/tests/analyze_metadata_embedding_text.py`（该文件使用 `from metaweave...`，迁移后更一致）

### 1.7 运行时/样例数据（需明确策略）

以下目录在 `nl2sql_v3/` 中并非纯运行时临时产物，部分文件（模板/样例）可能被测试或人工流程使用，需明确是否带入新项目：

- **输出目录（包含模板/样例）**
  - 源：`nl2sql_v3/output/metaweave/metadata/`
  - 建议：拆分处理
    - **建议迁移**：模板类文件（如 `_template*.json*`、`README_TEMPLATE.md`、`UPGRADE_TO_V2.md` 等）
    - **可选迁移**：具体业务数据样例（如 `public.*.json`）
  - 目标（扁平化）：`metaweave/output/`（内部子目录按新约定创建：`output/json`、`output/md`、`output/rel`、`output/cql`、`output/ddl`、`output/json_llm`）
- **缓存目录**
  - 源：`nl2sql_v3/cache/metaweave/`
  - 建议：默认不迁移（除非希望复用 `comment_cache.json`）
- **日志目录**
  - 源：`nl2sql_v3/logs/metaweave/`
  - 建议：不迁移

---

## 2. 迁移前检查（确认“目录外依赖/散落文档/路径硬编码”）

### 2.1 依赖扫描（只读）

迁移前应扫描以下类型引用，用于补齐迁移清单与后续替换范围（示例关键词）：

- Python import：
  - `src.metaweave`
  - `src.services`
- 路径硬编码：
  - `configs/metaweave/`
  - `output/metaweave/metadata/`
  - `logs/metaweave/`
  - `cache/metaweave/`
- 文档命令行示例：
  - `python -m src.metaweave...`
  - `configs/metaweave/...`

扫描范围（建议）：

- `nl2sql_v3/src/metaweave/`
- `nl2sql_v3/src/services/`
- `nl2sql_v3/configs/metaweave/`
- `nl2sql_v3/tests/`
- `nl2sql_v3/docs/`

产出物：

- 需要迁移的“目录外文件”列表（补齐第 1 节）
- 需要在新项目中替换/调整的“字符串清单”（用于第 3.4/3.5）

#### 2.1.1 建议扫描命令（示例，均为只读）

> 说明：环境中未必有 `rg`，以下以 `grep/find` 为准。

扫描 Python 导入（目录外依赖）：

```bash
grep -RInE --exclude-dir=__pycache__ "from src\\.services|import src\\.services" nl2sql_v3/src/metaweave
grep -RInE --exclude-dir=__pycache__ "from src\\.metaweave|import src\\.metaweave" nl2sql_v3/src/metaweave
```

扫描路径硬编码（用于扁平化）：

```bash
grep -RIn --exclude-dir=__pycache__ "configs/metaweave/" nl2sql_v3/src/metaweave nl2sql_v3/tests nl2sql_v3/scripts nl2sql_v3/docs
grep -RIn --exclude-dir=__pycache__ "output/metaweave/metadata/" nl2sql_v3/src/metaweave nl2sql_v3/tests nl2sql_v3/scripts nl2sql_v3/docs
grep -RIn --exclude-dir=__pycache__ "cache/metaweave/" nl2sql_v3/src/metaweave nl2sql_v3/tests nl2sql_v3/scripts nl2sql_v3/docs
grep -RIn --exclude-dir=__pycache__ "logs/metaweave/" nl2sql_v3/src/metaweave nl2sql_v3/tests nl2sql_v3/scripts nl2sql_v3/docs
```

---

## 3. 迁移步骤（仅对 metaweave/ 目录进行改动）

> 注意：本节包含“复制后在新项目中修改”的步骤，用于实现 `metaweave.*` + `/services` + 扁平化路径。  
> 这些修改全部发生在 `metaweave/` 新目录内，**不会触碰** `nl2sql_v3/`。

### 3.1 创建目标目录结构

在当前目录（仓库根，`nl2sql_v3/` 所在目录）创建项目目录 `metaweave/`：

```bash
mkdir -p metaweave
```

目录结构如下：

```
metaweave/
├── metaweave/          # Python 包：metaweave.*
├── services/           # Python 包：services.*
├── configs/            # 扁平化配置
├── scripts/
├── docs/design/
├── tests/
├── output/             # 扁平化输出
├── cache/
└── logs/
```

### 3.2 复制文件（Copy-only，包含隐藏文件）

复制时注意包含 dotfiles（如 `.gitkeep`），建议使用“复制目录内容”的写法（示例为 `cp -a SRC/. DEST/`）。

1) 复制 MetaWeave 包代码：

- `nl2sql_v3/src/metaweave/.` → `metaweave/metaweave/`

2) 复制 services（按最小子集）：

- `nl2sql_v3/src/services/__init__.py` → `metaweave/services/__init__.py`
- `nl2sql_v3/src/services/config_loader.py` → `metaweave/services/config_loader.py`
- `nl2sql_v3/src/services/db/.` → `metaweave/services/db/`
- `nl2sql_v3/src/services/vector_db/.` → `metaweave/services/vector_db/`

3) 复制配置文件：

- `nl2sql_v3/configs/metaweave/.` → `metaweave/configs/`
- `nl2sql_v3/src/configs/config.yaml` → `metaweave/configs/config.yaml`

4) 复制脚本：

- `nl2sql_v3/scripts/metaweave/.` → `metaweave/scripts/`

5) 复制文档（不使用 mv，避免引发“move”歧义）：

- `nl2sql_v3/docs/gen_rag/.` → `metaweave/docs/design/`

6) 复制测试：

- `nl2sql_v3/tests/unit/metaweave/.` → `metaweave/tests/unit/metaweave/`
- `nl2sql_v3/tests/metaweave_relationships/.` → `metaweave/tests/metaweave_relationships/`
- 选择性复制：`nl2sql_v3/tests/test_*matching*.py`、`nl2sql_v3/tests/test_dim_value_search.py`、`nl2sql_v3/tests/analyze_metadata_embedding_text.py`

### 3.3 复制/创建 .env（安全注意）

- 复制：`nl2sql_v3/.env` → `metaweave/.env`（仅本机使用）
- 创建：`metaweave/.env.example`（只保留变量名与占位符，**不得出现真实值**）

建议 `.env.example` 只包含如下形式（示例）：

```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=YOUR_DB
DB_USER=YOUR_USER
DB_PASSWORD=YOUR_PASSWORD

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=YOUR_PASSWORD
NEO4J_DATABASE=neo4j

DASHSCOPE_API_KEY=YOUR_KEY
DASHSCOPE_BASE_URI=https://dashscope.aliyuncs.com/compatible-mode/v1

DEEPSEEK_API_KEY=YOUR_KEY
DEEPSEEK_BASE_URI=https://api.deepseek.com/v1

MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_DATABASE=nl2sql
```

### 3.4 新项目代码改造：导入路径替换（仅 metaweave/ 目录内）

将新项目中所有 Python 文件的导入做如下替换：

1) `from src.metaweave...` / `import src.metaweave...` → `from metaweave...` / `import metaweave...`
2) `from src.services...` / `import src.services...` → `from services...` / `import services...`

同时修正文档/脚本/测试中的命令示例：

- `python -m src.metaweave.cli.main ...` → `python -m metaweave.cli.main ...`

#### 3.4.1 批量替换命令（在新项目 `metaweave/` 目录内执行）

> ⚠️ 仅在 `metaweave/` 新目录中执行，禁止在 `nl2sql_v3/` 下执行。  
> WSL/GNU sed 可用；如在 macOS 需要调整 `sed -i` 参数。
>
> 说明：`sed` 的正则在不同平台差异较大（例如 `\b` 并非通用“单词边界”语义），因此这里使用“精确字符串替换”以保证可执行性与可预期性。

替换 Python 导入：

```bash
cd metaweave
find . -name "*.py" -type f -print0 | xargs -0 sed -i \
  -e 's/from src\.metaweave/from metaweave/g' \
  -e 's/import src\.metaweave/import metaweave/g' \
  -e 's/from src\.services/from services/g' \
  -e 's/import src\.services/import services/g'
```

替换测试/脚本/文档中的命令示例（按需扩大/缩小文件类型范围）：

```bash
find . -type f \( -name "*.md" -o -name "*.sh" -o -name "*.txt" \) -print0 | xargs -0 sed -i \
  -e 's/python -m src\.metaweave/python -m metaweave/g' \
  -e 's/src\.metaweave/metaweave/g' \
  -e 's/src\.services/services/g'
```

### 3.5 新项目代码改造：路径扁平化（configs/ 与 output/）

#### 3.5.1 配置文件路径（YAML）

将新项目 `metaweave/configs/*.yaml` 中的路径从：

- `configs/metaweave/...` → `configs/...`
- `output/metaweave/metadata/...` → `output/...`
- `cache/metaweave/...` → `cache/...`
- `logs/metaweave/...` → `logs/...`

建议新项目约定的输出结构（扁平化）：

```
output/
├── ddl/
├── md/
├── json/
├── json_llm/
├── rel/
└── cql/
```

#### 3.5.2 代码默认值（CLI/测试/loader）

由于代码中存在默认路径常量/默认参数，扁平化必须同步修改新项目内的默认值，例如：

- `configs/metaweave/metadata_config.yaml` → `configs/metadata_config.yaml`
- `output/metaweave/metadata/md` → `output/md`

范围：`metaweave/`（包代码）+ `tests/` + `scripts/` + `docs/`（命令示例）

#### 3.5.3 批量替换命令（在新项目 `metaweave/` 目录内执行）

替换 YAML 配置中的路径：

```bash
cd metaweave
find configs -type f \( -name "*.yaml" -o -name "*.yml" \) -print0 | xargs -0 sed -i \
  -e 's|configs/metaweave/|configs/|g' \
  -e 's|output/metaweave/metadata/|output/|g' \
  -e 's|cache/metaweave/|cache/|g' \
  -e 's|logs/metaweave/|logs/|g'
```

替换 Python/测试中的默认路径字符串（示例，按需调整）：

```bash
find . -name "*.py" -type f -print0 | xargs -0 sed -i \
  -e 's|configs/metaweave/|configs/|g' \
  -e 's|output/metaweave/metadata/|output/|g' \
  -e 's|cache/metaweave/|cache/|g' \
  -e 's|logs/metaweave/|logs/|g'
```

### 3.6 修改 services/config_loader.py（仅新项目内）

为了配合“configs 扁平化”，需要将新项目 `metaweave/services/config_loader.py` 的默认配置路径从：

- `project_root/src/configs/config.yaml`

改为：

- `project_root/configs/config.yaml`

同时 `.env` 仍从 `project_root/.env` 加载（该行为符合新项目预期）。

#### 3.6.1 具体修改位置（示例）

在新项目 `metaweave/services/config_loader.py` 的 `ConfigLoader.__init__()` 中，存在默认配置路径设置（源项目对应逻辑如下）：

修改前（概念示例）：

```python
project_root = self._get_project_root()
config_path = project_root / "src" / "configs" / "config.yaml"
```

修改后：

```python
project_root = self._get_project_root()
config_path = project_root / "configs" / "config.yaml"
```

> 注意：这里只改新项目 `metaweave/services/config_loader.py`，不改 `nl2sql_v3/src/services/config_loader.py`。

#### 3.6.2 同步修正 `_get_project_root()`（关键）

原因：`nl2sql_v3/src/services/config_loader.py` 原本位于 `.../nl2sql_v3/src/services/`，其 `_get_project_root()` 通过 `current_file.parents[2]` 返回 `nl2sql_v3/` 根目录；但复制到新项目后文件路径变为 `metaweave/services/config_loader.py`，`parents[2]` 会变成仓库根目录（`cursor_2025h2/`），导致默认读取 `.env`/`configs/config.yaml` 位置错误。

因此新项目必须同步修改 `_get_project_root()`，让它返回 `metaweave/` 目录。

修改前（概念示例）：

```python
current_file = Path(__file__).resolve()
return current_file.parents[2]
```

修改后（推荐最小改动）：

```python
current_file = Path(__file__).resolve()
return current_file.parents[1]  # services/ -> metaweave/
```

更稳健的做法（可选）：向上查找 `pyproject.toml` 或 `configs/config.yaml` 所在目录作为项目根，避免未来文件层级变动导致再次出错。

### 3.7 新项目工程化文件（需要新建/调整）

需要在 `metaweave/` 根目录创建（或从模板生成）：

- `pyproject.toml`
- `README.md`（项目级）
- `.gitignore`（至少忽略 `.env`、`output/`、`cache/`、`logs/`）
- `pytest.ini`（如要运行测试）

`pyproject.toml` 的关键点（口径）：

- CLI entry：`metaweave = "metaweave.cli.main:cli"`
- 包包含：`metaweave` 与 `services`

#### 3.7.1 `pyproject.toml` 的 packages 配置建议（setuptools）

新项目采用“平铺包”（`metaweave/` 与 `services/` 都在项目根下），可使用 `setuptools` 的 find 配置：

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["metaweave*", "services*"]
exclude = ["tests*", "docs*", "output*", "cache*", "logs*"]

[project.scripts]
metaweave = "metaweave.cli.main:cli"
```

> 前提：`metaweave/metaweave/__init__.py` 与 `metaweave/services/__init__.py` 都存在（否则不会被识别为包）。

#### 3.7.2 `pyproject.toml` 完整示例（参考）

> 说明：以下为可工作的参考模板，依赖列表按源项目 `nl2sql_v3/pyproject.toml` 中的 MetaWeave 相关依赖整理；如后续发现缺失，以运行/测试报错为准补齐。

```toml
[project]
name = "metaweave"
version = "0.1.0"
description = "Database metadata generation and enhancement platform"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "click>=8.1.7",
  "dashscope>=1.14.0",
  "jinja2>=3.1.2",
  "langchain>=1.0.0",
  "langchain-community>=0.4.1",
  "langchain-openai>=0.2.0",
  "neo4j>=5.15.0",
  "numpy>=2.3.4",
  "pandas>=2.1.3",
  "pgvector>=0.2.0",
  "psycopg[binary]>=3.1.0",
  "psycopg-pool>=3.2.7",
  "pydantic>=2.5.2",
  "pymilvus>=2.6.5",
  "python-dotenv>=1.0.0",
  "PyYAML>=6.0.0",
  "sqlparse>=0.4.4",
  "tqdm>=4.66.1",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.4.2",
  "pytest-asyncio>=0.24.0",
  "pytest-cov>=4.1.0",
  "black>=23.0.0",
  "ruff>=0.1.0",
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["metaweave*", "services*"]
exclude = ["tests*", "docs*", "output*", "cache*", "logs*"]

[project.scripts]
metaweave = "metaweave.cli.main:cli"
```

### 3.8 使用 `uv` 管理虚拟环境（手工执行）

本项目要求使用 `uv` 管理虚拟环境与依赖。迁移过程中**不要自动创建**任何虚拟环境；请在迁移完成后由你在 WSL 环境中**手工**执行（WSL 对应虚拟环境目录为 `.venv-wsl`）：

```bash
cd metaweave

# 手工创建虚拟环境（WSL）
uv venv .venv-wsl

# 手工安装/同步依赖
uv sync
```

---

## 4. 迁移后验证清单（最小可运行）

### 4.1 结构验证

- `metaweave/metaweave/__init__.py` 存在
- `metaweave/services/__init__.py` 存在
- `metaweave/configs/config.yaml` 存在
- `metaweave/.env` 存在（本机）

### 4.2 导入验证

- `python -c "import metaweave; import services; print('ok')"`

### 4.3 CLI 验证

- `python -m metaweave.cli.main --help`

### 4.4 配置加载验证

- `services.config_loader.ConfigLoader()` 能默认加载 `configs/config.yaml` 且完成 `${VAR}` 替换（依赖 `.env`）

### 4.5 清理验证（确保替换完整）

检查是否仍残留旧导入/旧路径字符串：

```bash
# 在仓库根执行（或按需调整路径）

# Python 导入残留
grep -RIn --include="*.py" "src\.metaweave" metaweave && echo "发现遗漏：src.metaweave" || echo "OK: src.metaweave 已清理"
grep -RIn --include="*.py" "src\.services" metaweave && echo "发现遗漏：src.services" || echo "OK: src.services 已清理"

# 路径残留（代码/文档/测试）
grep -RIn "output/metaweave/metadata" metaweave && echo "发现遗漏：output/metaweave/metadata" || echo "OK: output 路径已清理"
grep -RIn "configs/metaweave/" metaweave && echo "发现遗漏：configs/metaweave/" || echo "OK: configs 路径已清理"
```

---

## 5. 风险与注意事项

- **最常见失败点**：只复制 `nl2sql_v3/src/metaweave` 会因缺少 `src.services.*` 依赖而无法运行（本规划已补齐到 `metaweave/services`）
- **扁平化带来的连锁修改**：不仅改 YAML，还必须改代码默认值、测试脚本、文档命令示例
- **安全**：任何文档、示例、提交记录中都不应包含真实 API Key/密码；一旦泄露应立即轮换

### 5.1 `.env` 路径类变量检查（建议）

迁移时建议快速检查 `.env` 中是否存在路径类变量（除 `LOG_FILE` 外），以避免写入到 `nl2sql_v3` 目录结构：

```bash
grep -nE '(^|_)(PATH|DIR|FILE)=' metaweave/.env || true
```


---

## 6. 附录：执行脚本（可选）

可在正式迁移时补充 `scripts/migrate.sh`（只操作 `metaweave/` 目录，且不含任何敏感信息），用于重复执行复制与替换流程。
