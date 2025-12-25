# json_llm 基于 json 增强式改造规划

## 1. 目标概述

将 `--step json_llm` 从"独立生成简化版 JSON"改造为"基于 json 全量输出的增强式处理"，实现以下核心目标：

1. **执行串行化**：json_llm 不再独立运行，它的隐含过程是，先执行 `--step json` 生成全量 JSON，然后再基于全量 JSON 进行 LLM 增强
2. **表类型覆盖**：直接使用 LLM 分类结果覆盖 json 的规则引擎分类结果(table_profile.table_category)，同时修改同级别下 "table_profile.confidence"属性的结果值为LLM的分类评估值。
3. **注释智能补全**：检查并补充缺失的表/字段注释，支持覆盖模式(在yaml文件中通过参数控制)
4. **消除数据库访问**：json_llm 仅在隐含的 --step json阶段查询数据库，它完全基于 json 文件调用LLM进行处理。
5. **输出目录统一**：输出统一到 `output/json` 目录，不再使用 `output/json_llm`
6. **简化 JSON 结构**：从 `--step json` 阶段移除未使用的 `fact_table_info`、`dim_table_info`、`bridge_table_info` 字段，避免维护成本和兼容性问题
7. **Token 成本优化**：表分类为固定策略（每表必调 LLM 且覆盖，含 `unknown`），Token 优化主要通过“裁剪输入视图”降低噪声；注释仅在缺失/覆盖时生成，并支持分批，避免无谓 token 消耗

## 2. 现状分析

### 2.1 当前架构

**--step json**（规则引擎方式）：

- 入口：`metaweave/cli/metadata_cli.py` → `MetadataGenerator`
- 实现：`metaweave/core/metadata/generator.py`
- 数据流：从 `output/ddl/*.sql` 读取 DDL（`DDLLoader`）→（仍需连库）查询行数+采样/统计 → 规则分类 → 全量 JSON 输出
- 输出目录：`output/json`
- 输出内容：包含完整的 `semantic_analysis`、`role_specific_info`、`logical_keys`、`table_profile`（含规则推断的 `confidence`、`inference_basis`）等

**--step json_llm**（LLM增强方式）：

- 入口：`metaweave/cli/metadata_cli.py` → `LLMJsonGenerator`
- 实现：`metaweave/core/metadata/llm_json_generator.py`
- 数据流：读取DDL文件名 → **直接查询数据库** → 采样 → LLM分类+注释生成 → 简化JSON输出
- 输出目录：`output/json_llm`
- 输出内容：仅包含基础信息 + LLM生成的 `table_category` 和 `comment`，**缺失** `semantic_analysis`、`role_specific_info`、`logical_keys` 等规则引擎生成的字段

### 2.2 核心问题

1. **重复的数据库访问**：json 和 json_llm 都查询数据库进行采样，造成资源浪费
2. **信息丢失**：json_llm 生成的简化版 JSON 丢失了规则引擎的语义分析结果
3. **输出割裂**：两个目录存放不同版本的 JSON，下游需要选择使用哪个
4. **无法比对验证**：规则引擎和 LLM 的分类结果无法直接比对和追溯
5. **未使用字段冗余**：json 输出包含 `fact_table_info`/`dim_table_info`/`bridge_table_info` 字段，但项目中无任何代码使用，造成维护负担

## 3. 改造方案

### 3.1 执行流程设计（两阶段串行）

```
用户执行：metaweave metadata --config config.yaml --step json_llm

阶段 A：全量 JSON 生成（复用现有 json 逻辑）
├── 调用 MetadataGenerator.generate(step="json")
├── DDL 解析或数据库元数据提取
├── 数据库采样与统计
├── 规则引擎语义分析（semantic_analysis、role_specific_info）
├── 逻辑主键检测（logical_keys）
├── 规则引擎表分类（table_category、confidence、inference_basis）
└── 输出到 output/json/*.json（全量 JSON）

阶段 B：LLM 增强（基于全量 JSON，定点修改）
├── 读取 output/json/*.json
├── 构建 LLM 输入视图（最小改动版 Token 优化：不喂全量 JSON，只保留必要字段，避免规则推断字段对 LLM 产生锚定）
├── 并发调用 LLM 获取：
│   ├── table_category（表类型）
│   ├── confidence（可选）
│   ├── reason（判断依据）
│   └── comment（表/字段注释）
├── 比对与覆盖：
│   ├── 表类型：比对规则引擎结果，以 LLM 为准覆盖
│   ├── 相关字段：同步更新 confidence、inference_basis 等
│   └── 规则结果备份：保存到 *_rule_based 字段
├── 注释增强：
│   ├── 缺失补全：补充空白的注释
│   └── 覆盖模式：根据配置覆盖已有注释
└── 写回 output/json/*.json（原地更新或原子替换）
```

### 3.2 表类型比对与覆盖逻辑

#### 3.2.0 固定策略：每表必调 LLM 并覆盖（含 unknown）

本方案的定位是：**只要执行 `--step json_llm`，就无条件使用 LLM 返回的 `table_category` 覆盖规则引擎结果**，即便 LLM 返回 `unknown` 也要覆盖。

因此：
- 不提供“跳过分类/部分分类”的策略开关；如果不希望用 LLM 分类，直接不要运行 `--step json_llm`。
- Token 优化重点放在“裁剪输入视图”和“注释按需/分批”，而不是跳过分类调用。

#### 3.2.1 读取与准备

```python
# 读取规则引擎结果
rule_category = json["table_profile"]["table_category"]  # fact/dim/bridge/unknown
rule_confidence = json["table_profile"]["confidence"]
rule_inference_basis = json["table_profile"]["inference_basis"]

# 调用 LLM 获取结果
llm_result = call_llm(table_json)
llm_category = llm_result["table_category"]
llm_confidence = llm_result.get("confidence", 0.9)  # LLM 也返回置信度
llm_reason = llm_result.get("reason", "")  # LLM 返回判断理由（可选，仅用于日志，不存储到 JSON）
```

#### 3.2.2 覆盖策略

**核心原则**：只要 LLM 返回了 `table_category`（包括 `unknown`），就用 LLM 结果覆盖（包括 `table_category` 和 `confidence`），同时备份规则引擎结果；如果 LLM 未返回 `table_category`，则保持规则引擎结果并记录告警。

```python
# 核心判断：只要 LLM 返回了 table_category（含 unknown），就覆盖
if llm_category:
    # 记录是否发生了类型变化（仅用于日志和后续处理）
    category_changed = (llm_category != rule_category)

    # 日志记录
    if category_changed:
        logger.warning(
            "表 %s 分类不一致: 规则=%s(%.2f) vs LLM=%s(%.2f) - 采用LLM结果",
            table_name, rule_category, rule_confidence or 0,
            llm_category, llm_confidence
        )
    else:
        logger.info(
            "表 %s 分类一致: %s - 更新为LLM的confidence(%.2f)",
            table_name, llm_category, llm_confidence
        )

    # 1. 备份规则引擎结果（无论是否一致，都备份）
    json["table_profile"]["table_category_rule_based"] = rule_category
    json["table_profile"]["confidence_rule_based"] = rule_confidence
    json["table_profile"]["inference_basis_rule_based"] = rule_inference_basis

    # 2. 覆盖为 LLM 结果（无论是否一致，都覆盖）
    json["table_profile"]["table_category"] = llm_category
    json["table_profile"]["confidence"] = llm_confidence
    json["table_profile"]["inference_basis"] = ["llm_inferred"]

    # 3. 标记来源
    json["table_profile"]["table_category_source"] = "llm"

else:
    # LLM 未返回 table_category：保持规则引擎结果
    logger.warning("表 %s LLM 未返回 table_category，保持规则引擎结果: %s", table_name, rule_category)
```

### 3.3 注释补充/覆盖逻辑

#### 3.3.0 按需调用判断（Token 优化）

为避免对注释已齐全的表调用 LLM，需要先分析哪些注释需要生成，并将"需要生成的字段列表"明确传给 LLM：

```python
def _analyze_comment_needs(self, table_json: Dict) -> Dict:
    """分析哪些注释需要生成（返回明确的字段列表）"""
    if not self.comment_generation_enabled:
        return {
            "need_table_comment": False,
            "columns_need_comment": [],
        }

    table_info = table_json.get("table_info", {})
    column_profiles = table_json.get("column_profiles", {})

    # 判断表注释是否需要生成
    table_comment = (table_info.get("comment") or "").strip()
    need_table_comment = self.generate_table_comment and ((not table_comment) or self.overwrite_existing)

    # 判断哪些列注释需要生成（返回明确的列名列表）
    columns_need_comment = []
    if self.generate_column_comment:
        for col_name, col_data in column_profiles.items():
            col_comment = (col_data.get("comment") or "").strip()
            if (not col_comment) or self.overwrite_existing:
                columns_need_comment.append(col_name)

    return {
        "need_table_comment": need_table_comment,
        "columns_need_comment": columns_need_comment,  # 明确的列名列表
    }
```

**调用判断**：
```python
comment_needs = self._analyze_comment_needs(table_json)
need_comments = (
    comment_needs["need_table_comment"] or
    len(comment_needs["columns_need_comment"]) > 0
)

if not need_comments:
    logger.info(f"表 {table_name} 注释已齐全，跳过注释生成")
    # 不调用注释生成任务
```

**关键优化**：将 `columns_need_comment` 列表明确传递给 LLM prompt，避免 LLM 为不需要的列生成注释，浪费 token。

**大表/覆盖模式的分批策略（建议实现，仍属“小改动”）**：
- 当 `overwrite_existing=true` 或者缺失注释列很多时，`columns_need_comment` 可能非常长，单次 prompt 容易超 token，且模型可能无法完整返回所有列注释。
- 复用现有配置 `comment_generation.max_columns_per_call` + `comment_generation.enable_batch_processing`：
  - 若 `enable_batch_processing=true` 且 `len(columns_need_comment) > max_columns_per_call`：将列名列表按 `max_columns_per_call` 分批，多次调用“仅注释任务 Prompt”，逐批合并 `column_comments`。
  - 第一批可以与分类合并（使用“组合任务 Prompt”），后续批次只跑“仅注释任务 Prompt”。
  - 若分批被禁用：只处理前 `max_columns_per_call` 个列，并记录 warning，避免误以为“已全量覆盖”。

示意伪代码：
```python
if need_comments and comment_needs["columns_need_comment"]:
    cols = comment_needs["columns_need_comment"]
    max_cols = comment_config.get("max_columns_per_call", 120)
    enable_batch = comment_config.get("enable_batch_processing", True)

    if enable_batch and len(cols) > max_cols:
        batches = [cols[i:i+max_cols] for i in range(0, len(cols), max_cols)]
        # 第1批：可与分类合并
        # 后续批：comments_only
    elif len(cols) > max_cols:
        cols = cols[:max_cols]
        logger.warning("列注释任务过多且分批被禁用，仅处理前 %s 个列", max_cols)
```

#### 3.3.1 判断缺失

```python
def is_comment_missing(comment: Optional[str]) -> bool:
    """判断注释是否缺失"""
    return not comment or comment.strip() == ""
```

#### 3.3.2 补充策略

```python
# 表注释
if is_comment_missing(json["table_info"]["comment"]):
    if llm_result.get("table_comment"):
        json["table_info"]["comment"] = llm_result["table_comment"]
        json["table_info"]["comment_source"] = "llm_generated"
elif config["overwrite_existing"]:
    # 备份原注释（仅首次备份，保证幂等性）
    if "comment_original" not in json["table_info"]:
        json["table_info"]["comment_original"] = json["table_info"]["comment"]
        json["table_info"]["comment_source_original"] = json["table_info"]["comment_source"]
    # 覆盖
    json["table_info"]["comment"] = llm_result["table_comment"]
    json["table_info"]["comment_source"] = "llm_generated"

# 字段注释（同理）
for col_name, col_profile in json["column_profiles"].items():
    if is_comment_missing(col_profile["comment"]):
        if col_name in llm_result.get("column_comments", {}):
            col_profile["comment"] = llm_result["column_comments"][col_name]
            col_profile["comment_source"] = "llm_generated"
    elif config["overwrite_existing"]:
        # 备份原注释（仅首次备份，保证幂等性）
        if "comment_original" not in col_profile:
            col_profile["comment_original"] = col_profile["comment"]
            col_profile["comment_source_original"] = col_profile["comment_source"]
        col_profile["comment"] = llm_result["column_comments"][col_name]
        col_profile["comment_source"] = "llm_generated"
```

### 3.4 数据库访问消除

#### 3.4.1 现状问题

`LLMJsonGenerator.generate_all_from_ddl()` 当前流程：
```python
# 读取 DDL 文件名
ddl_files = list(ddl_dir.glob("*.sql"))
for ddl_file in ddl_files:
    schema, table = self._parse_ddl_filename(ddl_file.stem)

    # ❌ 直接查询数据库获取元数据
    metadata = self.extractor.extract_all(schema, table)

    # ❌ 直接查询数据库采样
    sample_data = self.connector.sample_table(...)
```

#### 3.4.2 改造方案

**完全移除数据库依赖**，改为读取 json 文件：

```python
# 新方法：基于 json 目录增强
def enhance_json_directory(self, json_dir: Path) -> int:
    """基于已有的 json 文件进行 LLM 增强"""
    json_files = list(json_dir.glob("*.json"))

    for json_file in json_files:
        # ✅ 读取现有的全量 JSON
        with open(json_file, 'r', encoding='utf-8') as f:
            table_json = json.load(f)

        # ✅ 从 JSON 中获取所有需要的信息（无需查数据库）
        # - 元数据：table_info, column_profiles
        # - 采样数据：sample_records
        # - 统计信息：column_profiles.*.statistics

        # 构建 LLM 输入视图（裁剪 Token）
        llm_input = self._build_llm_input_view(table_json)

        # 调用 LLM
        llm_result = self._call_llm_for_enhancement(llm_input)

        # 合并结果
        enhanced_json = self._merge_llm_result(table_json, llm_result)

        # ✅ 原子写回（先写临时文件再替换）
        self._atomic_write_json(json_file, enhanced_json)
```

### 3.5 输出目录统一

#### 3.5.1 配置调整

```yaml
output:
  output_dir: "output"
  json_directory: "output/json"  # 统一输出目录
  json_llm_directory: "output/json_llm"  # legacy：新 json_llm 默认不写该目录（可选兼容复制）
```

#### 3.5.2 CLI 调整

```python
# metadata_cli.py
if step == "json_llm":
    # 阶段 A：生成全量 JSON
    click.echo("📊 阶段 1/2: 生成全量 JSON...")
    generator = MetadataGenerator(config, connector)
    count = generator.generate(step="json")  # 输出到 output/json

    # 阶段 B：LLM 增强
    click.echo("🤖 阶段 2/2: LLM 增强处理...")
    enhancer = JsonLlmEnhancer(config, connector)  # connector 仅用于配置，不查库
    json_dir = Path(config["output"]["json_directory"])
    enhanced_count = enhancer.enhance_json_directory(json_dir)  # 原地增强

    click.echo(f"✅ 完成！增强了 {enhanced_count} 个表")
```

## 4. 技术设计

### 4.1 新增模块：JsonLlmEnhancer

```python
# metaweave/core/metadata/json_llm_enhancer.py

class JsonLlmEnhancer:
    """基于全量 JSON 的 LLM 增强处理器"""

    def __init__(self, config: Dict, connector: Optional[DatabaseConnector] = None):
        """
        Args:
            config: 完整配置
            connector: 数据库连接器（仅用于传递配置，不实际查库）
        """
        self.config = config
        self.llm_service = LLMService(config.get("llm", {}))

        # 配置项
        # 注释生成配置（沿用现有 configs/metadata_config.yaml 的 comment_generation.*）
        comment_config = config.get("comment_generation", {})
        self.comment_generation_enabled = comment_config.get("enabled", True)
        self.generate_table_comment = comment_config.get("generate_table_comment", True)
        self.generate_column_comment = comment_config.get("generate_column_comment", True)
        self.overwrite_existing = comment_config.get("overwrite_existing", False)
        self.max_columns_per_call = comment_config.get("max_columns_per_call", 120)
        self.enable_batch_processing = comment_config.get("enable_batch_processing", True)

        # 异步配置
        langchain_config = config.get("llm", {}).get("langchain_config", {})
        self.use_async = langchain_config.get("use_async", False)

    def enhance_json_directory(self, json_dir: Path) -> int:
        """增强整个目录的 JSON 文件（同步入口）"""
        if self.use_async:
            return self._run_async(self._enhance_json_directory_async(json_dir))
        return self._enhance_json_directory_sync(json_dir)

    def _enhance_json_directory_sync(self, json_dir: Path) -> int:
        """同步增强（逐表处理；分类必做，注释按需）"""
        json_files = list(json_dir.glob("*.json"))
        enhanced_count = 0
        skipped_count = 0

        for json_file in json_files:
            try:
                table_json = self._load_json(json_file)
                table_name = table_json["table_info"]["table_name"]

                # 固定策略：每表必调 LLM 分类并覆盖
                need_classification = True
                comment_needs = self._analyze_comment_needs(table_json)
                need_comments = (
                    comment_needs["need_table_comment"] or
                    len(comment_needs["columns_need_comment"]) > 0
                )

                # 说明：分类必做，因此不会因为“都不需要”而跳过

                # 构建输入视图和 prompt
                llm_input = self._build_llm_input_view(table_json)

                if need_comments:
                    prompt = self._build_combined_prompt(llm_input, comment_needs)
                else:
                    prompt = self._build_classification_only_prompt(llm_input)

                # 同步调用 LLM
                response = self.llm_service._call_llm(prompt)
                llm_result = self._parse_llm_response(response, table_name)

                # 合并并写回
                enhanced = self._merge_llm_result(table_json, llm_result, need_comments)
                self._atomic_write_json(json_file, enhanced)
                enhanced_count += 1
            except Exception as e:
                logger.error("增强失败 %s: %s", json_file.name, e)

        logger.info("JSON 增强完成，共 %s 个文件（跳过 %s 个）", enhanced_count, skipped_count)
        return enhanced_count

    async def _enhance_json_directory_async(self, json_dir: Path) -> int:
        """异步增强（批量并发；分类必做，注释按需）"""
        json_files = list(json_dir.glob("*.json"))

        # 准备任务（仅包含需要增强的表）
        jobs = []
        skipped_count = 0
        for idx, json_file in enumerate(json_files):
            try:
                table_json = self._load_json(json_file)
                table_name = table_json["table_info"]["table_name"]

                # 固定策略：每表必调 LLM 分类并覆盖
                need_classification = True
                comment_needs = self._analyze_comment_needs(table_json)
                need_comments = (
                    comment_needs["need_table_comment"] or
                    len(comment_needs["columns_need_comment"]) > 0
                )

                # 说明：分类必做，因此不会因为“都不需要”而跳过

                # 构建 prompt
                llm_input = self._build_llm_input_view(table_json)
                if need_comments:
                    prompt = self._build_combined_prompt(llm_input, comment_needs)
                else:
                    prompt = self._build_classification_only_prompt(llm_input)

                jobs.append({
                    "idx": idx,
                    "file": json_file,
                    "table_json": table_json,
                    "table_name": table_name,
                    "prompt": prompt,
                    "need_comments": need_comments,
                })
            except Exception as e:
                logger.error("加载失败 %s: %s", json_file.name, e)

        if not jobs:
            logger.info("未发现可增强的 JSON 文件（或均加载失败）")
            return 0

        # 批量异步调用 LLM
        prompts = [job["prompt"] for job in jobs]

        def on_progress(done: int, total: int):
            if total:
                logger.info("LLM 增强进度: %s/%s", done, total)

        results = await self.llm_service.batch_call_llm_async(prompts, on_progress=on_progress)

        # 合并并写回（按 idx 映射，避免错位）
        enhanced_count = 0
        result_map = {idx: response for idx, response in results}

        for job in jobs:
            try:
                response = result_map.get(job["idx"], "")
                if not response:
                    logger.warning("LLM 响应为空: %s", job["file"].name)
                    continue

                llm_result = self._parse_llm_response(response, job["table_name"])

                # 合并并原子写入
                enhanced = self._merge_llm_result(job["table_json"], llm_result, job["need_comments"])
                self._atomic_write_json(job["file"], enhanced)
                enhanced_count += 1
            except Exception as e:
                logger.error("合并写入失败 %s: %s", job["file"].name, e)

        logger.info("JSON 异步增强完成，共 %s 个文件（跳过 %s 个）", enhanced_count, skipped_count)
        return enhanced_count

    def _run_async(self, coro):
        """在无事件循环场景运行协程"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        raise RuntimeError("检测到已存在运行中的事件循环，请在外部 await 调用或自行管理事件循环。")

    def _analyze_comment_needs(self, table_json: Dict) -> Dict:
        """分析哪些注释需要生成（返回明确的字段列表，Token 优化）"""
        table_info = table_json.get("table_info", {})
        column_profiles = table_json.get("column_profiles", {})

        # 判断表注释是否需要生成
        table_comment = (table_info.get("comment") or "").strip()
        need_table_comment = (not table_comment) or self.overwrite_existing

        # 判断哪些列注释需要生成（返回明确的列名列表）
        columns_need_comment = []
        for col_name, col_data in column_profiles.items():
            col_comment = (col_data.get("comment") or "").strip()
            if (not col_comment) or self.overwrite_existing:
                columns_need_comment.append(col_name)

        return {
            "need_table_comment": need_table_comment,
            "columns_need_comment": columns_need_comment,  # 明确的列名列表
        }

    def _build_llm_input_view(self, table_json: Dict) -> Dict:
        """构建 LLM 输入视图（Token 优化裁剪）"""
        # 最小改动版裁剪策略（先做这个，改动小、收益大）：
        # - 不把全量 JSON 原样塞给 LLM：成本高，且 logical_keys/semantic_analysis 等字段会“锚定”LLM
        # - 只提供 LLM 做判断真正需要的“事实类信息”：
        #   1) table_info（表名/已有注释）
        #   2) column_profiles（列名/类型/可空/已有注释/结构标记/必要统计）
        #   3) sample_records（样例值域；注意：json 输出里 sample_records 已经由 formatter 固定最多 5 行，因此 json_llm 不再二次截断行数）
        #   4) physical_constraints（PK/FK/UK/索引）
        # - 明确不传入这些规则推断/采样推断结论字段（减少噪声与误导）：
        #   - table_profile.logical_keys
        #   - column_profiles.*.semantic_analysis / role_specific_info
        #   - table_profile.inference_basis / confidence（规则引擎结论）
        #   - table_profile.column_statistics / fact_table_info / dim_table_info / bridge_table_info

        # 防御式访问所有字段
        table_info = table_json.get("table_info", {})
        column_profiles = table_json.get("column_profiles", {})
        sample_records = table_json.get("sample_records", {})
        table_profile = table_json.get("table_profile", {})

        return {
            "table_info": {
                "schema_name": table_info.get("schema_name", ""),
                "table_name": table_info.get("table_name", ""),
                "comment": table_info.get("comment", ""),
            },
            "column_profiles": self._simplify_column_profiles(column_profiles),
            # 直接复用 json 文件中的 sample_records（不做二次行/列截断；列数再多也不“放弃表”）
            "sample_records": self._normalize_sample_records(sample_records),
            "physical_constraints": table_profile.get("physical_constraints", {
                "primary_key": None,
                "foreign_keys": [],
                "unique_constraints": [],
                "indexes": []
            }),
        }

    def _simplify_column_profiles(self, column_profiles: Dict) -> Dict:
        """简化列画像（保留 LLM 需要的关键字段）"""
        simplified = {}
        for col_name, col_data in column_profiles.items():
            # 防御式访问 statistics（可能为 None 或缺失）
            original_stats = col_data.get("statistics") or {}

            simplified[col_name] = {
                "column_name": col_data.get("column_name", col_name),
                "data_type": col_data.get("data_type", "unknown"),
                "is_nullable": col_data.get("is_nullable", True),
                "comment": col_data.get("comment", ""),
                "statistics": {
                    "sample_count": original_stats.get("sample_count", 0),
                    "unique_count": original_stats.get("unique_count", 0),
                    "null_rate": original_stats.get("null_rate", 0.0),
                    "uniqueness": original_stats.get("uniqueness", 0.0),
                    "value_distribution": self._limit_value_distribution(
                        original_stats.get("value_distribution", {})
                    ),
                },
                "structure_flags": col_data.get("structure_flags", {}),
            }
        return simplified

    def _normalize_sample_records(self, sample_records: Dict) -> Dict:
        """规范化 sample_records（仅做缺省填充，不做行/列截断）"""
        if not sample_records:
            return {"sample_method": "none", "sample_size": 0, "total_rows": 0, "records": []}
        records = sample_records.get("records", []) or []
        return {
            "sample_method": sample_records.get("sample_method", "random"),
            "sample_size": sample_records.get("sample_size", len(records)),
            "total_rows": sample_records.get("total_rows", 0),
            "sampled_at": sample_records.get("sampled_at"),
            "records": records,
        }

    def _limit_value_distribution(self, value_dist: Dict, top_k: int = 10) -> Dict:
        """限制值分布的条目数（防止过大）"""
        if not value_dist:
            return {}

        # 按频次排序，保留 top_k
        sorted_items = sorted(value_dist.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_items[:top_k])

    def _merge_llm_result(
        self,
        table_json: Dict,
        llm_result: Dict,
        need_comments: bool
    ) -> Dict:
        """合并 LLM 结果到全量 JSON（按需合并）"""
        enhanced = copy.deepcopy(table_json)

        # 1. 表类型覆盖策略（固定执行：每表必调 LLM 分类并覆盖，含 unknown）
        rule_category = enhanced["table_profile"]["table_category"]
        rule_confidence = enhanced["table_profile"].get("confidence")
        rule_inference_basis = enhanced["table_profile"].get("inference_basis", [])

        llm_category = llm_result.get("table_category")
        llm_confidence = llm_result.get("confidence", 0.9)
        llm_reason = llm_result.get("reason", "")  # 可选，仅用于日志，不存储到 JSON

        if llm_category is not None:
            category_changed = (llm_category != rule_category)
            if category_changed:
                logger.warning(
                    "表 %s 分类不一致: 规则=%s(%.2f) vs LLM=%s(%.2f) - 采用LLM结果（含unknown）",
                    enhanced["table_info"]["table_name"],
                    rule_category, rule_confidence or 0,
                    llm_category, llm_confidence
                )
            else:
                logger.info(
                    "表 %s 分类一致: %s - 更新为LLM的confidence(%.2f)",
                    enhanced["table_info"]["table_name"],
                    llm_category, llm_confidence
                )

            # 备份规则引擎结果（无论是否一致，都备份）
            enhanced["table_profile"]["table_category_rule_based"] = rule_category
            enhanced["table_profile"]["confidence_rule_based"] = rule_confidence
            enhanced["table_profile"]["inference_basis_rule_based"] = rule_inference_basis

            # 覆盖为 LLM 结果（无论是否一致，都覆盖；llm_category=unknown 也覆盖）
            enhanced["table_profile"]["table_category"] = llm_category
            enhanced["table_profile"]["confidence"] = llm_confidence
            enhanced["table_profile"]["inference_basis"] = ["llm_inferred"]
            enhanced["table_profile"]["table_category_source"] = "llm"
        else:
            logger.warning(
                "表 %s LLM 未返回 table_category，无法覆盖，保持规则引擎结果: %s",
                enhanced["table_info"]["table_name"],
                rule_category
            )

        # 2. 注释增强（仅当调用了注释任务时执行）
        if need_comments:
            self._merge_table_comment(enhanced, llm_result)
            self._merge_column_comments(enhanced, llm_result)

        # 3. 更新元数据
        # - 保留 json 步骤写入的 generated_at（避免改写“生成时间”的语义）
        # - 新增 llm_enhanced_at 记录增强时间（便于追溯）
        enhanced["metadata_version"] = table_json.get("metadata_version", "2.0")
        enhanced["llm_enhanced_at"] = datetime.now(timezone.utc).isoformat()

        return enhanced

    def _merge_table_comment(self, enhanced: Dict, llm_result: Dict):
        """合并表注释"""
        current_comment = enhanced["table_info"].get("comment", "")
        llm_comment = llm_result.get("table_comment")

        if not llm_comment:
            return

        if not current_comment or current_comment.strip() == "":
            # 缺失补全
            enhanced["table_info"]["comment"] = llm_comment
            enhanced["table_info"]["comment_source"] = "llm_generated"
        elif self.overwrite_existing:
            # 覆盖模式（仅首次备份，保证幂等性）
            if "comment_original" not in enhanced["table_info"]:
                enhanced["table_info"]["comment_original"] = current_comment
                enhanced["table_info"]["comment_source_original"] = enhanced["table_info"].get("comment_source", "")
            enhanced["table_info"]["comment"] = llm_comment
            enhanced["table_info"]["comment_source"] = "llm_generated"

    def _merge_column_comments(self, enhanced: Dict, llm_result: Dict):
        """合并字段注释"""
        llm_comments = llm_result.get("column_comments", {})

        for col_name, col_profile in enhanced["column_profiles"].items():
            if col_name not in llm_comments:
                continue

            current_comment = col_profile.get("comment", "")
            llm_comment = llm_comments[col_name]

            if not current_comment or current_comment.strip() == "":
                # 缺失补全
                col_profile["comment"] = llm_comment
                col_profile["comment_source"] = "llm_generated"
            elif self.overwrite_existing:
                # 覆盖模式（仅首次备份，保证幂等性）
                if "comment_original" not in col_profile:
                    col_profile["comment_original"] = current_comment
                    col_profile["comment_source_original"] = col_profile.get("comment_source", "")
                col_profile["comment"] = llm_comment
                col_profile["comment_source"] = "llm_generated"

    def _load_json(self, file_path: Path) -> Dict:
        """加载 JSON 文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _parse_llm_response(self, response: str, table_name: str) -> Dict:
        """解析 LLM 响应（复用 llm_json_generator.py 的逻辑）"""
        try:
            # 更健壮的 JSON 提取（允许 LLM 输出 markdown/前后解释，只取第一个完整 JSON 对象）
            import re
            cleaned = (response or "").strip()

            # 移除开头的 ```json 或 ```
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
            # 移除结尾的 ```
            cleaned = re.sub(r'\s*```\s*$', '', cleaned, flags=re.MULTILINE).strip()

            start_idx = cleaned.find("{")
            if start_idx == -1:
                logger.error("LLM 响应未找到 JSON 对象 (表: %s): %s", table_name, cleaned[:200])
                return {}

            brace_count = 0
            end_idx = None
            for i in range(start_idx, len(cleaned)):
                if cleaned[i] == "{":
                    brace_count += 1
                elif cleaned[i] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break

            if end_idx is None:
                logger.error("LLM 响应 JSON 括号不匹配 (表: %s): %s", table_name, cleaned[:200])
                return {}

            json_text = cleaned[start_idx:end_idx]
            return json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.error("解析 LLM 响应失败 (表: %s): %s\n响应内容: %s", table_name, e, response[:200])
            return {}

    def _atomic_write_json(self, file_path: Path, data: Dict):
        """原子写入 JSON（先写临时文件再替换）"""
        temp_file = file_path.with_suffix(".tmp")
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_file.replace(file_path)
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            raise e
```

### 4.2 LLM Prompt 调整（分类必做 + 注释按需/分批）

为了降低 token 成本并支持“列注释分批”，提供两类主 Prompt + 1 个分批注释 Prompt：

#### 4.2.1 组合任务 Prompt（分类 + 注释）

```python
def _build_combined_prompt(self, llm_input_view: Dict, comment_needs: Dict) -> str:
    """构建组合任务 Prompt（分类 + 注释）"""
    # 构建注释任务描述（明确要生成的列名列表，避免模型擅自扩展）
    comment_tasks = []
    if comment_needs["need_table_comment"]:
        comment_tasks.append("- 为表生成描述性注释（table_comment）")
    if comment_needs["columns_need_comment"]:
        cols_str = "、".join(comment_needs["columns_need_comment"][:10])
        if len(comment_needs["columns_need_comment"]) > 10:
            cols_str += f"等 {len(comment_needs['columns_need_comment'])} 个列"
        comment_tasks.append(f"- 为以下列生成注释：{cols_str}")
        comment_tasks.append("- column_comments 只能包含上述列名，不得生成其他列的注释")

    return f"""
你是一名数据仓库建模专家，请根据我提供的"表结构"和"样例数据"完成任务。

## 表结构与样例数据
{json.dumps(llm_input_view, ensure_ascii=False, indent=2)}

注意：
1) 我提供的是"裁剪后的输入视图"，并非全量 JSON；这是为了减少 token 成本并避免噪声字段影响判断。
2) 请重点参考 sample_records（样例值域）与 physical_constraints（物理约束）进行判断与推理。
3) 特别注意：我并未提供 logical_keys 字段（逻辑主键推断），因为该字段基于采样数据推断，可能不准确。
   请仅基于 physical_constraints.primary_key（物理主键）和样例数据进行判断，不要依赖或假设存在逻辑主键。

## 任务一：判断表的类型（table_category）
1) fact：事实类表，特征：有度量值、随业务增长、含多维度外键
2) dim：维度类表，特征：描述性字段多、较稳定、以ID标识实体
3) bridge：桥接表，特征：用于多对多关系，通常只包含外键
4) unknown：无法判断时选择，不要强行猜测

请给出：
- table_category：表类型（fact/dim/bridge/unknown）
- confidence：置信度（0-1之间的小数）
- reason：判断理由（简短说明，1-2句话，可选，仅用于日志记录）

## 任务二：生成缺失的注释
{chr(10).join(comment_tasks)}

**重要**：
- 仅为上述明确列出的字段生成注释，不要生成其他字段的注释
- 如果本次没有需要生成列注释的字段，请返回 `"column_comments": {}`（空对象）
- 注释应简洁、准确、描述业务含义
- 使用中文

## 输出格式（JSON）
{{
  "table_category": "<fact|dim|bridge|unknown>",
  "confidence": 0.95,
  "reason": "判断理由",
  "table_comment": "表的业务含义（仅当任务二需要时）",
  "column_comments": {{
    "<col_name>": "列注释"
  }}
}}

请只返回 JSON，不要包含其他内容。
"""
```

#### 4.2.2 仅分类任务 Prompt

```python
def _build_classification_only_prompt(self, llm_input_view: Dict) -> str:
    """构建仅分类任务 Prompt（Token 优化）"""
    return f"""
你是一名数据仓库建模专家，请根据我提供的表结构判断表的类型。

## 表结构
{json.dumps(llm_input_view, ensure_ascii=False, indent=2)}

注意：
1) 我提供的是"裁剪后的输入视图"，并非全量 JSON
2) 请重点参考 sample_records（样例值域）与 physical_constraints（物理约束）进行判断
3) 特别注意：我并未提供 logical_keys 字段，请仅基于 physical_constraints.primary_key 和样例数据判断

## 任务：判断表的类型（table_category）
1) fact：事实类表，特征：有度量值、随业务增长、含多维度外键
2) dim：维度类表，特征：描述性字段多、较稳定、以ID标识实体
3) bridge：桥接表，特征：用于多对多关系，通常只包含外键
4) unknown：无法判断时选择，不要强行猜测

## 输出格式（JSON）
{{
  "table_category": "<fact|dim|bridge|unknown>",
  "confidence": 0.95,
  "reason": "判断理由（1-2句话）"
}}

请只返回 JSON，不要包含其他内容。
"""
```

#### 4.2.3 仅注释任务 Prompt

```python
def _build_comments_only_prompt(self, llm_input_view: Dict, comment_needs: Dict) -> str:
    """构建仅注释任务 Prompt（Token 优化）"""
    # 构建任务描述
    task_items = []
    if comment_needs["need_table_comment"]:
        task_items.append("1. 为表生成描述性注释（table_comment）")
    if comment_needs["columns_need_comment"]:
        cols_str = "、".join(comment_needs["columns_need_comment"][:10])
        if len(comment_needs["columns_need_comment"]) > 10:
            cols_str += f"等 {len(comment_needs['columns_need_comment'])} 个列"
        task_items.append(f"2. 为以下列生成注释：{cols_str}")

    return f"""
你是一名数据仓库建模专家，请根据表结构生成注释。

## 表结构
{json.dumps(llm_input_view, ensure_ascii=False, indent=2)}

## 任务
{chr(10).join(task_items)}

**重要**：
- 仅为上述明确列出的字段生成注释，不要生成其他字段的注释
- 如果本次没有需要生成列注释的字段，请返回 `"column_comments": {}`（空对象）
- 注释应简洁、准确、描述业务含义
- 使用中文

## 输出格式（JSON）
{{
  "table_comment": "表注释（仅当任务1需要时）",
  "column_comments": {{
    "<col_name>": "列注释"
  }}
}}

请只返回 JSON，不要包含其他内容。
"""
```

### 4.3 配置调整

```yaml
# configs/metadata_config.yaml

comment_generation:
  enabled: true                 # 总开关
  generate_table_comment: true  # 调用LLM自动补充缺失的表注释
  generate_column_comment: true # 调用LLM自动补充缺失的字段注释
  language: zh                  # 注释语言：zh / en / bilingual
  max_columns_per_call: 120     # 单批处理的缺失字段上限
  enable_batch_processing: true # 超过上限时自动分批
  overwrite_existing: false     # 默认不覆盖已有注释
  fallback_on_parse_error: true # 解析失败时使用降级策略

output:
  output_dir: "output"
  json_directory: "output/json"  # 统一输出目录
  json_llm_directory: "output/json_llm"  # legacy：新 json_llm 默认不写该目录（可选兼容复制）
```

**说明**：
- 注释开关都在 `configs/metadata_config.yaml` 的 `comment_generation.*` 下：
  - `comment_generation.enabled`：总开关
  - `comment_generation.generate_table_comment` / `comment_generation.generate_column_comment`：分别控制表/字段注释生成
  - `comment_generation.overwrite_existing`：是否覆盖已有注释（覆盖时建议开启分批）
- `sample_records` 的行数无需在 json_llm 再次控制：`--step json` 生成 JSON 时已由 `OutputFormatter` 固定最多写入 5 条样例记录。
- 表分类不提供额外开关：只要执行 `--step json_llm` 就每表必调 LLM 并覆盖（含 `unknown`）。如果不希望使用 LLM 分类，直接不要运行 `--step json_llm`。

## 5. 实施步骤

### 阶段 0：移除未使用的 *_table_info 字段
- [ ] 修改 `metaweave/core/metadata/models.py`
  - [ ] 从 `TableProfile` 数据类中移除 `fact_table_info`、`dim_table_info`、`bridge_table_info` 字段定义（第 483-485 行）
  - [ ] 从 `to_dict()` 方法中移除这三个字段的输出逻辑（第 515-520 行）
- [ ] 修改 `metaweave/core/metadata/profiler.py`
  - [ ] 移除 `_profile_table()` 方法中生成这三个字段的逻辑（第 506-508 行）
  - [ ] 移除或注释掉生成 `fact_info`/`dim_info`/`bridge_info` 的相关方法调用
- [ ] 验证：运行 `--step json`，确认输出的 JSON 不再包含这些字段

### 阶段 1：新增 JsonLlmEnhancer 模块
- [ ] 创建 `metaweave/core/metadata/json_llm_enhancer.py`
- [ ] 实现 `enhance_json_directory()` 方法
- [ ] 实现 `_build_llm_input_view()` 方法（Token 优化裁剪）
- [ ] 实现 `_merge_llm_result()` 方法（表类型比对与覆盖）
- [ ] 实现注释补充/覆盖逻辑
- [ ] 实现原子写入 `_atomic_write_json()`

### 阶段 2：调整 CLI 入口
- [ ] 修改 `metaweave/cli/metadata_cli.py` 中的 `--step json_llm` 逻辑
- [ ] 改为两阶段串行：先调用 json 步骤，再调用 enhancer
- [ ] 移除 json_llm 对数据库的直接访问

### 阶段 3：调整 LLM Prompt
- [ ] 修改 prompt 输出 schema，增加 `confidence` 和 `reason` 字段
- [ ] 调整 `_parse_llm_response()` 解析逻辑

### 阶段 4：配置调整
- [ ] 更新 `configs/metadata_config.yaml`
- [ ] 添加 `overwrite_existing` 配置说明
- [ ] 废弃 `json_llm_directory` 配置（保留兼容但不使用）

### 阶段 5：测试验证
- [ ] 单元测试：JsonLlmEnhancer 各方法
- [ ] 集成测试：完整的 json_llm 流程
- [ ] 验证点：
  - ✅ LLM 增强阶段不查库 / json_llm 不再单独查库
  - ✅ 输出 JSON 包含所有 json 步骤的字段
  - ✅ 表类型比对与覆盖正确
  - ✅ 规则引擎结果正确备份到 `*_rule_based` 字段
  - ✅ 注释补充/覆盖逻辑正确
  - ✅ 输出到 `output/json` 目录

### 阶段 6：文档更新
- [ ] 更新 README.md 说明 json_llm 的新行为
- [ ] 更新配置文档
- [ ] 添加迁移指南（针对已有用户）

## 6. 风险与注意事项

### 6.1 向后兼容性

**风险**：现有依赖 `output/json_llm` 目录的下游工具会失效

**缓解措施**：
- 保留 `json_llm_directory` 配置项（兼容模式）
- 提供迁移文档说明下游如何调整
- 可选：在 json_llm 完成后，复制一份到旧目录（过渡期）

### 6.2 Token 成本控制

**风险**：全量 JSON 直接喂给 LLM 可能导致 Token 爆炸

**缓解措施**：
- 实现严格的 Token 优化裁剪视图（`_build_llm_input_view`）
- 简化 statistics（只保留关键指标）
- 移除 `role_specific_info`、`logical_keys` 等冗余信息

### 6.3 语义一致性

**风险**：覆盖 `table_category` 后，如果不同步更新 `confidence`、`inference_basis`，会造成字段语义冲突

**缓解措施**：
- 强制要求 LLM 返回 `confidence` 和 `reason`
- 同步覆盖 `table_profile.confidence` 和 `table_profile.inference_basis`
- 将规则引擎结果备份到 `*_rule_based` 字段
- 新增 `table_category_source` 标记来源

### 6.4 文件原子性

**风险**：写入失败可能损坏原有的 JSON 文件

**缓解措施**：
- 使用临时文件 + 原子替换（`temp_file.replace(original_file)`）
- 异常时清理临时文件
- 可选：在增强前备份原文件

### 6.5 并发处理

**风险**：大量表并发调用 LLM 可能导致 API 限流或超时

**缓解措施**：
- 复用 `LLMService.batch_call_llm_async` 的并发控制
- 配置合理的 `batch_size` 和 `async_concurrency`
- 实现重试机制
- 失败时保留原值并记录日志

## 7. 下游影响说明（本次不改造）

### 7.1 受影响的下游模块

1. **rel_llm**（关系发现）
   - 当前：读取 `output/json_llm/*.json`
   - 影响：需要改为读取 `output/json/*.json`

2. **cql_llm**（CQL 生成）
   - 当前：读取 `output/json_llm/*.json`
   - 影响：需要改为读取 `output/json/*.json`

3. **其他可能的下游**
   - 任何直接读取 `json_llm` 目录的工具或脚本

### 7.2 迁移建议（留待后续）

本次改造**不包含**下游模块的修改，但提供迁移建议：

```python
# 修改前
json_dir = Path("output/json_llm")

# 修改后
json_dir = Path("output/json")

# 或从配置读取
json_dir = Path(config["output"]["json_directory"])
```

### 7.3 过渡方案

为了不影响现有下游，可以提供过渡期兼容：

```python
# 在 json_llm 完成后，可选复制到旧目录
if config.get("output", {}).get("json_llm_directory"):
    # 兼容模式：同时输出到旧目录
    shutil.copytree(json_dir, json_llm_dir, dirs_exist_ok=True)
    logger.warning("已复制到 json_llm 目录（兼容模式），建议下游迁移到 json 目录")
```

## 8. 预期收益

### 8.1 核心收益

1. **性能提升**：消除重复的数据库查询，减少约 50% 的数据库访问
2. **信息完整性**：json_llm 输出包含完整的规则引擎分析结果
3. **可追溯性**：保留规则引擎和 LLM 的双重结果，便于比对和分析
4. **维护性**：统一输出目录，简化下游集成
5. **灵活性**：支持注释覆盖模式，满足不同场景需求

### 8.2 Token 成本优化收益（裁剪视图 + 注释按需/分批）

#### 8.2.1 注释任务优化（按需 + 仅生成指定列）

**场景假设**：100 张表，其中 60% 表注释已齐全

| 优化前（每次都带注释任务） | 优化后（仅缺失/覆盖时带注释任务） | 节省率（注释相关） |
|--------|--------|--------|
| 100 次调用（分类+注释总是一起做） | 40 次调用（仅 40 张缺注释的表走“分类+注释”；其余 60 张走“仅分类”） | 60% |

**额外优化**：明确"需要生成的列名列表"避免 LLM 为不需要的列浪费 token
- 优化前：100 列表 × 平均 50 列 × 每列 50 tokens（生成不需要的注释）= 250K tokens
- 优化后：仅为需要的列生成（假设平均 20 列）= 100K tokens
- **节省 60% 注释生成 token**

#### 8.2.2 分类任务的“输入裁剪”收益（不跳过调用，但减少 token）

本方案的表分类为固定策略：每张表必调 LLM 并覆盖（含 unknown）。Token 优化主要来自：
- 不喂全量 JSON，改喂裁剪视图（移除 logical_keys/semantic_analysis 等噪声字段）
- 当不需要注释时使用“仅分类 Prompt”，避免携带注释任务描述与列清单

#### 8.2.3 综合收益估算

**假设**：
- 100 张表数据仓库
- 60% 表注释已齐全
- 注释策略：按需调用

**调用次数对比**：

| 任务组合 | 优化前 | 优化后 | 说明 |
|---------|--------|--------|------|
| 分类 only | 0 | 60 | 60 张表无需注释，仅做分类 |
| 分类 + 注释 | 100 | 40 | 40 张表缺注释，分类+注释合并一次调用 |
| **总调用次数** | **100** | **100** | 调用次数不变，但平均 prompt 更小 |

**Token 成本对比**（假设每次调用平均 3000 input tokens）：
- 优化前：100 × 3000 = 300K tokens（每次都带注释任务与更多字段）
- 优化后：60 × 2000 + 40 × 3000 = 240K tokens（分类 only 更短，且裁剪视图降低 token）
- **节省约 20%（示意）**

**实际成本节省**（以 GPT-4 Turbo 为例）：
- 输入 token：$10/1M → 节省 $0.9/100 表
- 输出 token：$30/1M → 节省约 $1.5/100 表（假设输出平均 1500 tokens）
- **总节省：约 $2.4/100 表**
- **对于 1000 张表：约 $24**

#### 8.2.4 策略选择建议

| 场景 | 推荐策略 | 理由 |
|------|---------|------|
| 注释齐全场景 | `comment_generation.enabled: false` | 完全跳过注释任务（仍会做分类覆盖） |
| 只补齐缺失注释 | `overwrite_existing: false` | 仅补齐缺失，最省 token |
| 强制覆盖全部注释 | `overwrite_existing: true` + 分批 | 输出一致性更强，但需要分批避免超 token |

## 9. 时间估算

- 阶段 1（核心模块）：2-3 天
- 阶段 2（CLI 调整）：0.5 天
- 阶段 3（Prompt 调整）：0.5 天
- 阶段 4（配置调整）：0.5 天
- 阶段 5（测试验证）：1-2 天
- 阶段 6（文档更新）：0.5 天

**总计**：5-7 工作日
