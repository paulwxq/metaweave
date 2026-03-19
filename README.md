# MetaWeave

**数据库元数据自动生成与关系发现平台**

MetaWeave 从 PostgreSQL 数据库中提取表结构元数据，通过规则引擎和大语言模型（LLM）自动补全中文注释、识别列语义角色、发现表间关联关系（根据数据库外键约束、规则评分、LLM根据表结构和样例数据推断），并将生成的结构化知识加载到 Neo4j 图数据库和 Milvus 向量数据库，为下游 NL2SQL 系统提供高质量的 RAG（Retrieval-Augmented Generation）检索基础。

---

## 核心功能

### 1. 元数据提取与 LLM 增强

- 自动提取表结构（DDL）、约束、索引等元信息
- 对表和字段进行数据画像（采样统计、枚举识别、语义角色标注）
- **LLM 自动补全中文注释**：即使源库没有任何 COMMENT，也能为每张表和每个字段生成中文业务描述
- **LLM 语义分类**：推断表的业务分类和所属主题域

### 2. 表关系发现

- **规则引擎**：基于主外键约束、列名相似度、数据包含率、Jaccard 指数等多维度评分，自动发现表间关联关系
- **LLM 增强**：即便数据库未定义主外键，也能通过 LLM 语义推理发现隐含的关联关系，并经数据库采样验证
- 支持单列关系和复合键关系发现
- 输出标准化的关系描述（含关系类型、基数、置信度评分）

### 3. Neo4j CQL 生成

- 基于发现的主外键和推断关系，自动生成 Neo4j Cypher 导入脚本
- 将表映射为节点、关系映射为边，构建完整的数据库知识图谱

### 4. 数据加载到向量数据库与图数据库

- **表结构加载**：将表的结构定义信息（列名、类型、注释、语义角色）向量化后加载到 Milvus
- **维表记录加载**：将维度表的实际记录（如部门名称、产品类别）向量化后加载到 Milvus
- **样例 SQL 加载**：将 LLM 生成的 Question-SQL 训练样例向量化后加载到 Milvus
- **关系图谱加载**：将表的关联关系通过 CQL 导入到 Neo4j

### 5. SQL RAG 样例生成

- 基于业务主题域配置和表结构文档，调用 LLM 批量生成 Question-SQL 训练样例
- 通过 SQL EXPLAIN 自动校验生成的 SQL 合法性
- 支持 LLM 自动修复校验失败的 SQL

---

## 项目定位

MetaWeave 是 **NL2SQL_V3** 项目的 RAG 数据生成器。NL2SQL_V3 负责将自然语言查询转换为 SQL，而 MetaWeave 负责为其准备检索增强所需的全部知识：

```
PostgreSQL ──→ MetaWeave ──→ Milvus (向量检索) ──→ NL2SQL_V3
                         ──→ Neo4j  (图谱查询) ──→ NL2SQL_V3
```

同时，MetaWeave 生成的关系图谱和元数据文档也可独立用于**数据库文档化**和**表间关系审计**。

---

## 技术栈

| 层次 | 技术 |
|------|------|
| 语言 | Python 3.12+ |
| CLI | Click |
| LLM | LangChain + 通义千问（Qwen）/ DeepSeek |
| Embedding | 通义千问 text-embedding-v3 |
| 源数据库 | PostgreSQL（psycopg 3 + 连接池） |
| 图数据库 | Neo4j（neo4j-python-driver） |
| 向量数据库 | Milvus（pymilvus）/ pgvector |
| 包管理 | uv |
| 配置 | YAML + .env 环境变量替换 |

---

## 快速开始

### 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd metaweave

# 创建虚拟环境并安装依赖（WSL / Linux）
uv venv .venv-wsl --python 3.12
source .venv-wsl/bin/activate
uv sync --active

# Windows 用户
uv venv .venv-win --python 3.12
.venv-win\Scripts\Activate.ps1
uv sync --active
```

### 配置

1. 复制 `.env.example` 为 `.env`，填入数据库连接和 LLM API Key：

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_database
DB_USER=postgres
DB_PASSWORD=your_password

DASHSCOPE_API_KEY=sk-xxxx
DASHSCOPE_BASE_URI=https://dashscope.aliyuncs.com/compatible-mode/v1
```

2. 编辑 `configs/metadata_config.yaml` 按需调整配置（通常默认即可）。

### 模块级 LLM 配置覆盖

MetaWeave 支持在全局 `llm` 配置的基础上，为特定模块单独覆盖 LLM 参数（深合并语义）。只需在对应模块的配置段下添加 `llm` 子键即可，未声明的字段自动继承全局配置。

**当前已支持模块级 LLM 覆盖的模块：**

| 模块 | 配置路径 | 说明 |
|------|---------|------|
| Domain Generation | `domain_generation.llm` | 业务域生成 |
| SQL RAG | `sql_rag.llm` | Question-SQL 生成与校验 |
| Relationships | `relationships.llm` | LLM 关系发现 |
| JSON LLM | `json_llm.llm` | LLM 增强 JSON 画像 |
| Comment Generation | `comment_generation.llm` | 注释生成 |

示例：为 SQL RAG 切换到更强的 Qwen 模型：

```yaml
sql_rag:
  llm:
    providers:
      qwen:
        model: qwen-max
```

> 所有五个模块均已完成模块级 LLM 覆盖接入。

### 两段式执行

MetaWeave 采用**两段式流水线**：先生成元数据产物，再加载到目标数据库。

**第一段：生成元数据**

```bash
# 标准流水线（规则引擎）：ddl → json → rel → cql
uv run metaweave pipeline generate -c configs/metadata_config.yaml --track standard

# LLM 增强流水线：ddl → json_llm → rel_llm → cql_llm
uv run metaweave pipeline generate -c configs/metadata_config.yaml --track llm
```

**第二段：加载数据**

```bash
# 加载全部：CQL → Neo4j，表结构/维表/SQL样例 → Milvus
uv run metaweave pipeline load -c configs/metadata_config.yaml
```

> 详细的命令参数和执行选项请参考 [docs/100_执行命令完整参考.md](docs/100_执行命令完整参考.md)。

---

## 输出产物

```
output/
├── ddl/    # 带注释的 DDL（含样例数据标注）
├── json/   # 表/列数据画像（规则 + LLM 增强）
├── rel/    # 表间关系发现结果（relationships_global.json）
├── cql/    # Neo4j Cypher 导入脚本
├── md/     # 人类可读的 Markdown 表结构文档
└── sql/    # LLM 生成的 Question-SQL 训练样例
```

---

## 项目结构

```
metaweave/
├── metaweave/
│   ├── cli/               # CLI 命令入口
│   ├── core/
│   │   ├── metadata/      # 元数据提取与生成
│   │   ├── relationships/ # 表关系发现
│   │   ├── cql_generator/ # Neo4j CQL 生成
│   │   ├── loaders/       # 数据加载器（Neo4j / Milvus）
│   │   └── sql_rag/       # SQL RAG 样例生成与校验
│   ├── services/          # LLM / Embedding 服务
│   └── utils/             # 工具函数
├── services/              # 配置加载 / 数据库连接管理
├── configs/               # YAML 配置文件
├── docs/                  # 设计文档与执行参考
├── tests/                 # 测试用例
└── output/                # 生成产物（git ignored）
```

---

## License

MIT
