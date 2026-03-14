# 101_generate_domains_md_context_enhancement.md

## 1. 需求背景与目标

### 1.1 背景
当前 `--generate-domains` 功能（用于自动生成数据库业务主题 `domains`）在执行时，主要依赖从 `configs/db_domains.yaml` 中人工提前填写的 `database.description`。这带来了两个显著的现状问题：
1. **内容质量依赖人工**：如果用户提供的描述过于简略，LLM 生成的业务主题分类往往不够准确，容易变成空洞的“套话”。
2. **初始化报错**：对于刚初始化的项目（`db_domains.yaml` 不存在时），系统会直接报错并要求用户去手动创建文件并填写 description。

虽然系统提供了 `--md-context` 系列参数，允许将真实数据库的表名和表注释（来自于 `output/md` 目录下的 Markdown 文件摘要）附加上去作为 LLM 的上下文参考，但这需要用户在命令行中显式指定，使用体验不够流畅。

### 1.2 改造目标
1. **强制开启 MD 上下文**：废弃 `--md-context` 作为可选开关的概念，强制在内部默认开启 MD 上下文，不再提供 `--no-md-context` 关闭选项，极大提高生成 domains 的准确性。其他相关参数的默认值保持不变。
2. **自动化初始化配置**：当 `configs/db_domains.yaml` 文件不存在时，系统不再报错，而是能够自动基于当前 MD 上下文初始化该文件。
3. **全自动信息生成**：初始化 `db_domains.yaml` 文件之后，要自动生成所有的内容，包括 `database.name`，`database.description` 和 `domains` 列表等。
4. **统一配置默认值**：自动在生成的配置文件中添加预设配置 `llm_inference.max_domains_per_table: 3`。
5. **代码不再根据数据库配置的 description 生成 domain**：对数据库的描述信息，不应该提前写在 `configs/db_domains.yaml` 文件中。本改造将彻底移除对 YAML 文件中 description 字段的读取依赖。允许在执行 `--generate-domains` 命令时通过新增的 `--description` 参数直接传入一句话描述。如果没有这个参数，就完全根据 md 文件的内容生成全部的 `db_domains.yaml` 文件。**无论是否传入该参数，最终写入 YAML 文件的 `database.description` 都是由 LLM 结合上下文和用户提示整理生成后的长文本。**
6. **动态提示词**：生成 `db_domains.yaml` 内容的提示词应该根据是否传递数据库描述参数，而使用不同的提示词。

---

## 2. 方案设计

### 2.1 CLI 参数调整 (`metaweave/cli/metadata_cli.py`)

#### 2.1.1 调整原有选项默认值
保留现有的 CLI 参数，但强制其核心逻辑开启：
- `--md-context`（**实现方式建议**：在 Click 中保留该 `is_flag` 参数以兼容旧命令，但它将变成无意义冗余。无论用户传不传该参数，代码内部都强制等价于启用 MD 上下文，并且不提供 `--no-md-context` 关闭选项）。
- `--md-context-dir`（维持独立覆盖功能，默认情况下的推断逻辑见 2.1.4 节）。
- `--md-context-mode`（保持现有逻辑和默认值 `name_comment`）。
- `--md-limit`（保持现有逻辑和默认值 `100`）。

#### 2.1.2 新增参数
- 增加 `--description`（推荐使用长选项，减少短选项冲突歧义）参数：
  - 允许用户在命令行直接输入对数据库的简短描述。
  - 示例：`uv run metaweave metadata -c configs/metadata_config.yaml --generate-domains --description "这是一个电商交易库"`。
  - **设计约束**：该参数的值会作为“用户补充说明”提交给 LLM，但**它不会被直接写入 YAML**。LLM 会结合 MD 摘要与此补充说明，返回一个整理之后、更为详细的 `database.description`，并以此覆盖用户在命令行提交的简述，最终写入 YAML。**注意：最终写入 YAML 的 description 与用户在命令行输入的简述不一致是完全预期的行为，这正是为了利用 LLM 扩写和丰富上下文。**

#### 2.1.3 前置校验与执行逻辑调整
- **移除** `if generate_domains: if not Path(domains_config).exists(): raise UsageError("文件不存在，请先创建并填写 database.description")` 的强制文件检查。
- **允许** `configs/db_domains.yaml` 不存在时直接运行 `--generate-domains`。
- **校验互斥行为**：现有代码中 `--generate-domains` 与 `--domain`/`--cross-domain` 存在复杂的互斥和强依赖 `domains` 列表非空的情况。**本次改造明确规定：**执行 `--generate-domains` 这一初始化/重生成路径时，**绝不应检查** `domains` 列表是否已存在或非空。该命令是一个预配置的前置操作，应该完全畅通无阻地生成文件。如果它和 `--domain` 等参数同时使用，则继续保持报错退出的互斥设计（**注意：报错的原因是因为 `--generate-domains` 和 `--domain` 两个命令在逻辑上是互斥的，而不是因为缺少 domains 列表**）。
- **不再回退** 读取 `configs/db_domains.yaml` 中的 `database.description`，完全以命令行的 `--description` 参数（如果有）和 MD 摘要作为生成的依据。
- **强化退出声明**：`--generate-domains` 功能被设计为“提前 return”的模式。只要传递了 `--generate-domains` 参数，程序会在生成 domains 列表并写入 YAML 文件后**直接返回**，即使在命令行中指定了 `--step all` 或其他步骤，也不会继续跑 `ddl/json/...` 的后续流程。

#### 2.1.4 `md_context_dir` 优先级规则
为保证 Markdown 上下文的读取路径更健壮，建立以下短平快的推断优先级：

1. **CLI 传参覆盖**：如果命令行显式出现了 `--md-context-dir` 选项（即使等于默认值），直接优先使用该路径。
2. **指定配置读取**：读取 `--config` 传入的 `metadata_config.yaml`，优先查找 `output.markdown_directory`。
3. **主目录推断**：如果上一步没找到，则查找 `output.output_dir` 并在后面追加 `/md`。
4. **硬编码兜底**：上述所有规则都失效时，回退使用 `output/md`。

### 2.2 DomainGenerator 核心逻辑重构 (`metaweave/core/metadata/domain_generator.py`)

#### 2.2.1 初始化逻辑 (`_load_yaml` & 模板生成)
- 文件不存在时不再抛出异常，而是为了保证与已有配置文件的字段顺序、注释习惯及多行文本格式（如 `description: |`）严格一致，在内存中初始化一个标准的 YAML 字符串模板或高级字典结构：
  ```yaml
  # 数据库业务主题配置
  database:
    name: ""
    description: |
      
  llm_inference:
    max_domains_per_table: 3
  domains:
  - name: _未分类_
    description: 无法归入其他业务主题的表
  ```
- 这样可以确保当 `configs/db_domains.yaml` 缺失时，我们能生成出带有正确注释和多行文本结构的“毛坯”配置。

#### 2.2.2 MD 摘要获取 (`_build_md_context`)
- 该方法由于 MD 上下文被强制开启，变为常规必执行步骤。如果根据上述优先级规则确定的 `md_dir` 不存在或为空，应抛出友好错误：“缺少 Markdown 摘要文件，请先运行 `metaweave metadata --step md`”。

#### 2.2.3 提示词动态路由 (`_build_prompt`)
- **根据是否传入 `--description` 动态选择 Prompt 模板。**

**场景 A：无 `--description` 参数（全自动模式）**
提示词模板：
```text
你是一个数据库业务分析专家。请根据以下提供的【表结构摘要】（包含表名和首行注释），生成该数据库的整体配置信息。

【表结构摘要】（最多 {limit} 个）
{md_summary_block}

## 任务
1. 分析这些表的业务范围，推断该数据库系统的整体用途。
2. 为该数据库起一个合适的名称（database.name）。
3. 编写一段详细的数据库范围概述（database.description，不少于50字，说明包含哪些核心数据模块）。
4. 基于上述分析，划分 3-8 个合理的业务主题类别（domains）。

## 注意事项
- 不要生成名为 "_未分类_" 的主题（这是系统预置的特殊主题，会自动添加）
- 只生成有明确业务含义的主题

## 输出格式（严格的 JSON）
```json
{{
  "database": {{
    "name": "推断出的系统名称",
    "description": "详细的数据库整体描述..."
  }},
  "domains": [
    {{"name": "主题1", "description": "主题1的职责描述"}},
    {{"name": "主题2", "description": "主题2的职责描述"}}
  ]
}}
```
请只返回 JSON，不要包含其他内容。
```

**场景 B：有 `--description` 参数（用户强指导模式）**
提示词模板：
```text
你是一个数据库业务分析专家。请根据以下提供的【表结构摘要】（包含表名和首行注释），以及【用户补充说明】，生成该数据库的整体配置信息。

【用户补充说明】
{user_description_block}

【表结构摘要】（最多 {limit} 个）
{md_summary_block}

## 任务
1. 分析这些表的业务范围，并结合用户的补充说明，推断该数据库系统的整体用途。
2. 为该数据库起一个合适的名称（database.name）。
3. 结合用户补充说明和表结构，编写一段详细的数据库范围概述（database.description，不少于50字，说明包含哪些核心数据模块。这会覆盖用户的原有简短说明）。
4. 基于上述分析，划分 3-8 个合理的业务主题类别（domains）。

## 注意事项
- 不要生成名为 "_未分类_" 的主题（这是系统预置的特殊主题，会自动添加）
- 只生成有明确业务含义的主题

## 输出格式（严格的 JSON）
```json
{{
  "database": {{
    "name": "推断出的系统名称",
    "description": "详细的数据库整体描述..."
  }},
  "domains": [
    {{"name": "主题1", "description": "主题1的职责描述"}},
    {{"name": "主题2", "description": "主题2的职责描述"}}
  ]
}}
```
请只返回 JSON，不要包含其他内容。
```

#### 2.2.4 解析与写入逻辑 (`_parse_response` & `write_to_yaml`)
- **解析**：解析 LLM 返回的完整 JSON（提取 `database` 和 `domains` 节点）。
- **合并**：
  - 更新内存字典中的 `database` 节点（包含推断出的 name 和 description。**LLM 返回的 description 强制覆盖命令行中提供的 `--description` 简短输入**）。
  - 确保注入预置的 `_未分类_` 主题到 `domains` 列表首位。
  - **强制注入固化参数**：在组装最终要写出的字典/配置时，强制注入配置项 `llm_inference: { max_domains_per_table: 3 }`。**这个参数是代码里写死的，不参与 LLM 提示词讨论；如果 LLM 在 JSON 里擅自“发散”返回了别的值，系统也会无视并强制覆盖为 3，绝不尊重 LLM。**
- **YAML 格式与结构一致性**：
  - 将合并后的字典数据原封不动地输出为 YAML 格式。
  - 为了保证 `database.description` 生成的多行文本在 YAML 文件中表现为友好的多行块样式（使用 `|` 标量），在输出 yaml 时建议配置 `yaml.Dumper` 的相关参数或借助特殊类型的格式化输出。
- **写入**：全量写入/覆盖 `configs/db_domains.yaml` 文件。

---

## 3. 执行流程示例

### 场景一：纯小白用户（首次执行，无文件）
```bash
uv run metaweave metadata -c configs/metadata_config.yaml --generate-domains
```
1. MD 上下文被强制开启。检测到 `configs/db_domains.yaml` 不存在，在内存中初始化默认字典。
2. 读取由 `metadata_config.yaml` 确定的 MD 目录，生成表摘要（默认前 100 张表）。
3. 构建**全自动模式 Prompt**（不含用户描述），发给 LLM。
4. LLM 返回推断出的库名、总描述、domains 列表。
5. 插入 `_未分类_` 和强制写死 `llm_inference` 节点，按一致的 YAML 多行文本格式生成完整的 `configs/db_domains.yaml`，然后**直接退出程序**（即使加了 `--step` 参数）。

### 场景二：带有针对性描述执行
```bash
uv run metaweave metadata -c configs/metadata_config.yaml --generate-domains --description "这只是一个用于测试边缘场景的日志库"
```
1. MD 上下文被强制开启。在内存中初始化（或读取已存在的配置）。
2. 读取由 `metadata_config.yaml` 确定的 MD 目录，生成表摘要。
3. 构建**补充模式 Prompt**，将 `--description` 传入的字符串放在【用户补充说明】部分。
4. LLM 结合这句简短的话和表结构摘要，返回更新后的库名、**更详细的综合总描述**（`database.description`）以及 domains 列表。
5. 将 LLM 返回的结构连同强制注入的 `llm_inference`，覆盖写入 `configs/db_domains.yaml` 并退出程序。

---

## 4. 影响评估与兼容性

1. **强依赖 `md` 步骤**：由于将 MD 上下文作为主要数据源基础，执行此命令前，用户必须已经成功执行过 `--step md`（通常通过 `--step ddl` + `--step md` 产生）。这是合理的，因为这本来就是流水线的前置产物。
2. **配置文件覆盖**：现有的 `db_domains.yaml` 会被重新生成覆盖（旧的 domain 列表和手动填写的 description 都会被覆盖重写）。这符合 `--generate-domains` 作为一个“重新生成配置”的工具命令的预期语义。
3. **CLI 体验极大提升**：多数情况下无需再手动加 `--md-context`，一键即可基于现有表结构冷启动业务域配置，但专家用户仍可用 `--md-context-dir/mode/limit` 覆盖默认行为。