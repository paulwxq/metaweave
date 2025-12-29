# semantic_role=complex：复杂类型字段过滤改造设计

## 背景与问题
当前关系发现（`--step rel` / `--step rel_llm`）对“不适合作为关联键”的复杂类型字段（如 `json/jsonb/array/bytea/geometry/...`）主要依赖 **类型兼容性阈值**（`single_column.min_type_compatibility` / `composite.min_type_compatibility`）来做过滤。

但这套机制存在一个缺口：**类型兼容性判断对“相同类型”默认给满分**（例如 `jsonb` vs `jsonb` 会被认为 `type_compatibility=1.0`），因此当列名相似度满足阈值时，复杂类型仍可能进入候选/评分流程，造成噪声关系或错误关系。

为让过滤更“语义化”和可配置化，计划引入新的字段语义角色：
- `semantic_role = "complex"`

并通过现有配置项：
- `single_column.exclude_semantic_roles`
- `composite.exclude_semantic_roles`

来统一过滤复杂类型字段（尤其是在目标列侧）。

## 目标
1. 元数据 JSON 中的 `column_profiles[*].semantic_analysis.semantic_role` 支持输出 `"complex"`。
2. `--step rel` 和 `--step rel_llm` 都能通过配置把 `complex` 排除掉，减少无意义候选与 LLM 噪声：
   - `rel`：在候选生成阶段过滤（CandidateGenerator）
   - `rel_llm`：在 LLM 返回解析后、评分前过滤（LLMRelationshipDiscovery）
3. 逻辑主键推断阶段也能自然排除 `complex`（复用现有 `exclude_semantic_roles` 配置）。

## 非目标
- 不调整 `RelationshipScorer` 的 `type_compatibility` 算法本身（仍保留现有族群兼容逻辑）。
- 不改变“物理约束不过滤语义角色”的总体原则：PK/UK/索引/外键等物理约束成员在候选生成阶段不做语义过滤（包括 `complex`）。

## 现状梳理（代码定位）
### 1) 语义角色判定入口
语义角色判断在 `metaweave/core/metadata/profiler.py`：
- `MetadataProfiler._classify_semantics()`：按优先级决定 `semantic_role`（audit/datetime/identifier/description/enum/metric/attribute）。

### 2) 关系候选过滤入口（现有）
关系候选过滤在 `metaweave/core/relationships/candidate_generator.py`：
- 单列候选：目标列（非物理约束）按 `single_column.exclude_semantic_roles` 过滤。
  - 不作用于：物理约束的目标列（PK/UK/索引）
  - 作用于：排除上面之外的普通列

- 复合候选：目标列按以下规则处理。
  - Stage 1（约束到约束匹配）：物理约束目标列不过滤；逻辑约束目标列在元数据生成阶段已过滤
  - Stage 2（动态同名匹配）：目标列不过滤（`is_physical=True` 硬编码）

- 类型兼容性：`_get_type_compatibility_score()` 对相同类型返回 `1.0`，因此复杂类型"同型"不会被类型兼容性挡住。

## 设计方案
### A. 元数据侧：增加 `complex` 语义角色
#### A1. 复杂类型识别规则
在 `MetadataProfiler._classify_semantics()` 中新增一段"complex detection"，优先级**必须**放在：
- `audit`、`datetime` 之后
- `identifier` 之前

原因：
- complex 类型不应被误判成 identifier/metric/attribute；
- audit/datetime 仍应保持最高优先级（避免 `updated_at jsonb` 这类极端命名冲突）。

固定的完整优先级顺序（从高到低）：
1. `audit`（基于命名模式）
2. `datetime`（基于类型 + 命名模式）
3. `complex`（新增，基于类型）
4. `identifier`（基于命名模式 + 约束/统计）
5. `description`（基于命名模式 + 类型/统计）
6. `enum`（基于统计特征）
7. `metric`（基于命名模式 + 数值类型）
8. `attribute`（默认兜底）

复杂类型集合（按 PostgreSQL 常见表述）：

**本阶段可识别的类型**（基于 `data_type`，可直接加入配置）：
  - JSON：`json`, `jsonb`
  - Array：`array`（匹配 `ARRAY` 类型声明）以及 `integer[]`、`text[]` 等数组后缀（通过 `endswith("[]")` 匹配）
  - KV/XML：`hstore`, `xml`
  - Binary：`bytea`
  - 全文搜索：`tsvector`, `tsquery`
  - PostgreSQL 内置几何类型：`point`, `line`, `lseg`, `box`, `path`, `polygon`, `circle`
    - 说明：这些类型在 DDL 中直接显示类型名，可以匹配

**后续引入 `udt_name` 后再启用**（当前阶段无法识别）：
  - PostGIS 扩展：`geometry`, `geography`（`data_type` 显示为 `USER-DEFINED`，需要 `udt_name` 才能识别）
  - 范围类型：`int4range`, `int8range`, `numrange`, `tsrange`, `tstzrange`, `daterange`（`data_type` 显示为 `USER-DEFINED`）

**可选类型**（视业务而定，默认不加入 `complex_types` 配置）：
  - 网络地址：`inet`, `cidr`, `macaddr`, `macaddr8`（有的系统会用 `inet` 做关联键）
  - 位串：`bit`, `bit varying`（`varbit`）

输出建议：
- `semantic_role="complex"`
- `semantic_confidence=0.95`（基于类型判断，确定性高；但 complex_types 也包含配置/策略成分，因此不取 1.0）
- `inference_basis` 增加类似：`complex_type:<type>` 或 `complex_type:array`

#### A1.1 将复杂类型列表配置化（必需）
在 `configs/metadata_config.yaml` 中**必须**增加 `column_profiling.complex_types` 配置，用于驱动 "complex detection"。

**配置说明**：
- `complex_types` 是"会被识别为 `semantic_role=complex` 的类型集合"，不是"排除名单"
- 是否排除（过滤）仍由 `single_column.exclude_semantic_roles` / `composite.exclude_semantic_roles` 决定
- 匹配规则：对 `data_type` 与 `complex_types` 都做 `lower()` 归一化，确保 `ARRAY/array` 等写法都能命中
- **未配置的影响**：如果不添加此配置项，`self.config.complex_types` 为空集，complex 检测逻辑不会命中任何列（功能实质关闭）

```yaml
column_profiling:
  complex_types:
    # 当前阶段可识别的类型（基于 data_type）
    - json
    - jsonb
    - array
    - hstore
    - xml
    - bytea
    - tsvector
    - tsquery
    # PostgreSQL 内置几何类型（data_type 直接显示类型名）
    - point
    - line
    - lseg
    - box
    - path
    - polygon
    - circle

    # 以下类型当前阶段无法识别（data_type 为 USER-DEFINED）
    # 需要引入 udt_name 后再启用
    # - geometry      # PostGIS
    # - geography     # PostGIS
    # - int4range     # range 类型
    # - int8range
    # - numrange
    # - tsrange
    # - tstzrange
    # - daterange

    # 可选：视业务而定（如需要可加入）
    # - inet
    # - cidr
    # - macaddr
    # - macaddr8
    # - bit
    # - varbit
```

说明：
- 该配置的作用是“哪些字段会被 profiler 标记为 `semantic_role=complex`”（分类层面）。
- 是否在关系发现阶段被过滤，仍由 `single_column.exclude_semantic_roles` / `composite.exclude_semantic_roles` 控制（过滤层面）。

complex detection 的类型来源与匹配规则（本阶段不引入 `udt_name`）：
1. **类型来源**：使用 `column.data_type`（来自 DDL 解析的 `DDLLoader._parse_data_type()`，已小写化的 base type）
2. **标准化处理**：对 `data_type` 执行 `.lower()` 归一化后，与 `complex_types` 配置进行匹配（忽略大小写）
3. **数组类型识别**（特殊规则）：
   - 若 `data_type.lower() == "array"`，判定为 `complex`（匹配 ARRAY 类型声明）
   - 或 `data_type.lower().endswith("[]")`，判定为 `complex`（匹配 `integer[]`、`text[]` 等数组后缀写法）
   - 注意：配置中的 `array` 项对应上述两种判断逻辑

#### A1.2 代码改造点位

**① 配置读取**：`metaweave/core/metadata/profiler.py`
- 位置：`ProfilingConfig` dataclass
- 修改内容：添加 `complex_types` 字段并在 `from_dict()` 中读取

**前置条件**（如果文件缺少以下 import，需要补充）：
```python
from typing import Set
from dataclasses import field
```

**新增字段**（在 `ProfilingConfig` dataclass 中）：
```python
# 新增：complex 类型集合（小写）
complex_types: Set[str] = field(default_factory=set)
```

**读取逻辑**（在 `ProfilingConfig.from_dict()` 中）：
```python
# 新增：读取 complex_types 配置
complex_types_list = config.get("column_profiling", {}).get("complex_types", [])
complex_types = set(t.lower() for t in complex_types_list)
```

**返回值**（在 `from_dict()` 的 return 语句中添加）：
```python
return cls(
    # ... 现有字段（不修改）...
    complex_types=complex_types,  # 新增此参数
)
```

**使用方式**（在 `MetadataProfiler._classify_semantics()` 中）：
```python
data_type_lower = column.data_type.lower()
if data_type_lower in self.config.complex_types:
    inference_basis.append(f"complex_type:{data_type_lower}")
    return (...)
```

**② Complex 检测逻辑**：`metaweave/core/metadata/profiler.py`
- 位置：`MetadataProfiler._classify_semantics()` 方法内（line 596）
- 插入位置：在 `datetime` 检测之后，`identifier` 检测之前（见 A1 优先级顺序）
- 修改内容：添加 complex 类型判断逻辑

**方法签名**（真实结构）：
```python
def _classify_semantics(
    self,
    column: ColumnInfo,
    stats: Optional[Dict],
    struct_flags: StructureFlags,
) -> Tuple[
    str,                           # semantic_role
    float,                         # confidence
    Optional[IdentifierInfo],      # identifier_info
    Optional[MetricInfo],          # metric_info
    Optional[DateTimeInfo],        # datetime_info
    Optional[EnumInfo],            # enum_info
    Optional[AuditInfo],           # audit_info
    Optional[DescriptionInfo],     # description_info
    List[str],                     # inference_basis
]:
```

**修改内容**（在 datetime 检测之后、identifier 检测之前插入）：
```python
# datetime detection (line 633-648, 现有代码)
if column.data_type.lower() in self.config.datetime_types or self._matches_datetime_name(lower_name):
    inference_basis.append("datetime_type_match" if ...)
    return (
        "datetime",
        confidence,
        None, None, DateTimeInfo(...), None, None, None,
        inference_basis,
    )

# ========== 新增：complex detection ==========
# 在 datetime 之后、identifier 之前插入
data_type_lower = column.data_type.lower()
# 检查1: 直接匹配 complex_types 配置（如 json, jsonb, hstore, xml, bytea, tsvector, tsquery, point, line, etc.）
# 检查2: 特殊处理数组类型 - 如果配置中包含 "array"，则匹配 ARRAY 类型或 xxx[] 后缀
is_complex = (
    data_type_lower in self.config.complex_types or
    ("array" in self.config.complex_types and data_type_lower.endswith("[]"))
)
if is_complex:
    inference_basis.append(f"complex_type:{data_type_lower}")
    return (
        "complex",                 # semantic_role
        0.95,                      # confidence
        None,                      # identifier_info
        None,                      # metric_info
        None,                      # datetime_info
        None,                      # enum_info
        None,                      # audit_info
        None,                      # description_info
        inference_basis,           # List[str]
    )

# identifier detection (line 650-666, 现有代码)
is_id, id_confidence, matched_pattern, id_basis = self._is_identifier(column, stats, struct_flags)
if is_id:
    inference_basis.extend(id_basis)
    return (
        "identifier",
        id_confidence,
        IdentifierInfo(...), None, None, None, None, None,
        inference_basis,
    )
```

**关键点**：
- 所有非 complex 的 info 对象都返回 `None`（IdentifierInfo、MetricInfo、DateTimeInfo 等）
- `inference_basis` 是 `List[str]`，需要用 `.append()` 添加推理依据
- 插入位置：line 649 之后（datetime 之后）、line 650 之前（identifier 之前）

**③ 输出格式**：
- `semantic_role`: `"complex"`
- `semantic_confidence`: `0.95`（基于类型判断，确定性高）
- `inference_basis`: `f"complex_type:{data_type}"`（如 `"complex_type:jsonb"`）

### B. 关系发现侧：利用 exclude_semantic_roles 排除 complex
#### B1. 配置约定（YAML）
在 `configs/metadata_config.yaml` 的以下配置中支持加入 `"complex"`：
- `single_column.exclude_semantic_roles`：用于单列候选时过滤目标列（非物理约束目标列）
- `composite.exclude_semantic_roles`：用于复合候选时过滤逻辑约束目标列

**默认值修改策略（唯一方案）**：

在现有 `exclude_semantic_roles` 列表末尾追加 `"complex"`，其他配置保持不变。

**操作步骤**：
1. 找到 `configs/metadata_config.yaml` 中的 `single_column.exclude_semantic_roles`
2. 在列表末尾追加 `"complex"`
3. 对 `composite.exclude_semantic_roles` 执行相同操作

**示例**：
- 现有配置：`["audit", "metric"]`
- 修改后：`["audit", "metric", "complex"]`

**原则**：
- 本次改造只新增 `"complex"` 过滤，不调整现有的 `audit`/`metric`/`description`/`attribute` 等配置
- 保持与现有过滤策略的连续性

**改造范围界定**：
- **B1（配置层）**：仅修改 YAML 默认值（在 `exclude_semantic_roles` 末尾追加 `"complex"`），不涉及代码逻辑变更
- **B2（代码逻辑层）**：新增"同名列例外"过滤规则（默认启用，无需配置开关），这是对过滤策略的实质性调整
- 两者独立：B1 约束"哪些语义角色被排除"，B2 约束"什么情况下例外放行"

#### B2. 目标列过滤例外规则
当前候选生成中有明确原则："目标列如果是物理约束（PK/UK/索引）则不过滤语义角色"。

本方案在当前阶段**扩展这条原则**，增加"同名列不过滤"规则：

**过滤优先级规则（从高到低）**：
1. **物理约束目标列**：PK/UK/索引 → 不过滤语义角色
2. **非物理约束目标列中，Complex 类型列**：`semantic_role="complex"` → 永远过滤（即使同名）
3. **非物理约束目标列中，同名列**：列名与源列完全相同（大小写不敏感）→ 不过滤其他语义角色
   - 单列同名：源列 = 目标列（忽略大小写）
   - 复合同名：对应位置逐列同名（忽略大小写），例如 `["a","b"]` vs `["A","B"]` 是同名，但 `["a","b"]` vs `["b","a"]` 不是同名
4. **其他目标列**：按 `exclude_semantic_roles` 配置过滤

**说明**：
- Complex 类型（jsonb/array/bytea等）本质上不适合做外键关联，即使同名同型（如 `orders.metadata` vs `products.metadata`）也大概率是"各自存储各自的元数据"，而非关联关系
- 因此 complex 过滤优先级高于同名匹配，确保复杂类型噪声被彻底排除

**适用范围**：
- **单列候选**：需要添加同名检查逻辑
- **复合候选**：
  - Stage 1（约束到约束）：逻辑主键在元数据生成阶段已过滤，此处不再二次过滤
  - Stage 2（动态同名）：已实现不过滤（`is_physical=True` 硬编码）

**作用范围说明**：
- 上述同名例外规则**仅用于目标列语义角色过滤**，不改变后续评分逻辑或关系方向判断
- 同名列仍会参与后续的 `inclusion_rate`、`jaccard_index`、`name_similarity` 等评分维度计算
- 该规则只是"允许同名列进入候选池"，不等同于"同名列一定会得高分/被产出为关系"

**代码改造点位**：

**① 单列候选**：`metaweave/core/relationships/candidate_generator.py`
- 位置：`_generate_single_column_candidates()` 方法，lines 877-897
- 修改内容：在语义角色过滤逻辑中添加同名检查

修改前：
```python
if target_has_physical:
    pass  # 物理约束不过滤
else:
    if target_role in self.exclude_semantic_roles:
        continue  # 按配置过滤
```

修改后：
```python
if target_has_physical:
    pass  # 物理约束不过滤
elif target_role == "complex":
    logger.debug(
        "[single_column_candidate] 跳过 complex 类型目标列: %s.%s (即使同名也过滤)",
        f"{target_schema}.{target_table_name}", target_col_name
    )
    continue  # complex 类型永远过滤（优先级高于同名）
elif col_name.lower() == target_col_name.lower():
    logger.debug(
        "[single_column_candidate] 同名列不过滤: %s.%s (role=%s)",
        f"{target_schema}.{target_table_name}", target_col_name, target_role
    )
    pass  # 同名列不过滤
else:
    if target_role in self.exclude_semantic_roles:
        continue  # 其他语义角色按配置过滤
```

**② 复合候选**：无需修改（但存在已知限制）
- Stage 1（约束到约束匹配）：本次无需新增改造点，complex 过滤已由上游（元数据生成阶段的逻辑主键检测）覆盖
- Stage 2（动态同名匹配）：`is_physical=True` 硬编码（line 331）→ 目标列语义角色过滤完全不生效

**⚠️ 已知限制**：
- **复合候选 Stage 2 无法过滤 complex 类型**
- 场景示例：源表复合 PK `(order_id, metadata jsonb)` + 目标表有同名列 → Stage 2 会产生包含 `metadata` 的复合关系
- 原因：Stage 2 的 `is_physical=True` 硬编码使得目标列不执行任何语义角色过滤（包括 complex）
- 影响范围：仅影响"源表物理约束包含 complex 列"的场景（实际较少见，因为 DBA 很少把 jsonb/array 加入 PK/UK）
- **本次实现**：不处理该场景（保持现有 Stage 2 逻辑不变）
- **未来可能方向**（不在本次范围）：修改 Stage 2 逻辑对 complex 做硬编码过滤，或在源表约束收集阶段就排除包含 complex 列的组合

#### B3. rel_llm 的语义角色过滤

**背景说明**：
- `--step rel_llm` 使用 `metaweave/core/relationships/llm_relationship_discovery.py`，**不依赖 `CandidateGenerator`**
- 当前实现中，LLM 推断的关系**不会自动应用 `exclude_semantic_roles` 过滤**
- 如果不对 `rel_llm` 做过滤改造，LLM 仍可能推断出包含 complex 类型的关系（如 `orders.metadata jsonb` → `products.metadata jsonb`）

**改造方案**：

**① 配置读取**：`metaweave/core/relationships/llm_relationship_discovery.py`
- 位置：`LLMRelationshipDiscovery.__init__()` 初始化时
- 修改内容：从配置中读取 `single_column.exclude_semantic_roles` 和 `composite.exclude_semantic_roles`
```python
self.single_exclude_roles = set(config.get("single_column", {}).get("exclude_semantic_roles", []))
self.composite_exclude_roles = set(config.get("composite", {}).get("exclude_semantic_roles", []))
```

**② 新增过滤方法**：`_filter_by_semantic_roles()`
- 位置：`LLMRelationshipDiscovery` 类内
- 功能：按语义角色过滤候选关系（与 `rel` 保持一致的过滤规则）
- 调用时机：在 `_finalize_relations()` 的 Stage 4 之后、Stage 5 之前（`_filter_existing_fks()` 之后、`_score_candidates()` 之前）

**代码示例**：
```python
def _filter_by_semantic_roles(
    self,
    candidates: List[Dict],
    tables: Dict[str, Dict]
) -> List[Dict]:
    """按语义角色过滤候选关系

    过滤范围说明：
    - 仅过滤目标列（to_cols），与 rel 保持一致
    - 源列（from_cols）不做语义过滤（理由：与 rel 的过滤侧保持一致，rel 只过滤目标列）

    过滤规则（优先级从高到低）：
    1. 物理约束目标列（PK/UK/索引）：不过滤语义角色
    2. 非物理约束目标列中，Complex 类型列：永远过滤（即使同名）
    3. 非物理约束目标列中，同名列：不过滤其他语义角色
    4. 其他目标列：按 exclude_semantic_roles 配置过滤

    Args:
        candidates: LLM 返回的候选关系
        tables: 表元数据字典（schema.table -> table_json）

    Returns:
        过滤后的候选关系
    """
    filtered = []
    skipped_count = 0

    for candidate in candidates:
        candidate_type = candidate["type"]

        # 根据候选类型选择过滤规则
        if candidate_type == "single_column":
            from_cols = [candidate["from_column"]]
            to_cols = [candidate["to_column"]]
            exclude_roles = self.single_exclude_roles
        else:  # composite
            from_cols = candidate["from_columns"]
            to_cols = candidate["to_columns"]
            exclude_roles = self.composite_exclude_roles

        # 检查目标列（仅过滤目标列，与 rel 一致）
        should_skip = False
        to_table_key = f"{candidate['to_table']['schema']}.{candidate['to_table']['table']}"
        to_table_json = tables.get(to_table_key)

        if not to_table_json:
            logger.warning(f"[filter_semantic_roles] 目标表 {to_table_key} 元数据缺失，跳过候选")
            # 预期丢弃：元数据缺失的候选无法进行后续评分，此处提前过滤
            continue

        # 判断是否同名（大小写不敏感）
        if candidate_type == "single_column":
            is_same_name = (from_cols[0].lower() == to_cols[0].lower())
        else:  # composite
            # 复合键同名定义：对应位置逐列同名（大小写不敏感）
            # 例如：["a","b"] vs ["A","B"] 是同名，但 ["a","b"] vs ["b","a"] 不是同名（位置不对应）
            is_same_name = (
                len(from_cols) == len(to_cols) and
                all(f.lower() == t.lower() for f, t in zip(from_cols, to_cols))
            )

        # 建立大小写不敏感的列名映射（用于查找列画像）
        # 注意：LLM 返回的列名大小写可能与 column_profiles 不一致
        # 假设前提：同一表内列名大小写不敏感且无冲突（PostgreSQL 列名不区分大小写，极少出现 Foo/foo 同时存在）
        # 已知限制：如果同表存在 "Foo" 和 "foo" 两列（极少见但理论可能），lower() 键会发生覆盖
        # 本次实现：不处理该极端情况（直接使用 lower() 映射）
        col_profile_map = {
            col_name.lower(): col_profile
            for col_name, col_profile in to_table_json.get("column_profiles", {}).items()
        }

        for to_col in to_cols:
            # 获取目标列画像（大小写不敏感查找）
            col_profile = col_profile_map.get(to_col.lower())
            if not col_profile:
                # 目标列画像缺失：预期丢弃该候选
                # 原因：缺失画像会导致后续评分阶段 type_compatibility 误判（可能被算成 1.0）
                logger.debug(
                    f"[filter_semantic_roles] 跳过候选（目标列 {to_col} 画像缺失）: "
                    f"{candidate['from_table']['schema']}.{candidate['from_table']['table']} → {to_table_key}"
                )
                should_skip = True
                skipped_count += 1
                break

            # 优先级 1: 检查是否为物理约束列
            structure_flags = col_profile.get("structure_flags", {})
            is_physical = (
                structure_flags.get("is_primary_key") or
                structure_flags.get("is_unique") or
                structure_flags.get("is_unique_constraint") or
                structure_flags.get("is_indexed")
            )

            if is_physical:
                continue  # 物理约束列不过滤

            # 获取语义角色
            semantic_role = col_profile.get("semantic_analysis", {}).get("semantic_role")

            # 优先级 2: Complex 永远过滤（即使同名）
            if semantic_role == "complex":
                logger.debug(
                    f"[filter_semantic_roles] 跳过候选（目标列 {to_col} 为 complex，即使同名也过滤）: "
                    f"{candidate['from_table']['schema']}.{candidate['from_table']['table']} → {to_table_key}"
                )
                should_skip = True
                skipped_count += 1
                break

            # 优先级 3: 同名列不过滤其他语义角色
            if is_same_name:
                continue  # 同名列跳过语义角色检查

            # 优先级 4: 其他列按配置过滤
            if semantic_role in exclude_roles:
                logger.debug(
                    f"[filter_semantic_roles] 跳过候选（目标列 {to_col} 为 {semantic_role}）: "
                    f"{candidate['from_table']['schema']}.{candidate['from_table']['table']} → {to_table_key}"
                )
                should_skip = True
                skipped_count += 1
                break

        if not should_skip:
            filtered.append(candidate)

    logger.info(
        f"[filter_semantic_roles] 过滤前: {len(candidates)}, 过滤后: {len(filtered)}, "
        f"跳过: {skipped_count}"
    )
    return filtered
```

**③ 调用位置**：`_finalize_relations()` 方法内（line 518）
- 位置：在 `_filter_existing_fks()` 之后、`_score_candidates()` 之前插入

修改前（line 531-542）：
```python
logger.info("阶段4: 过滤已有物理外键（基于 relationship_id）")
filtered_candidates = self._filter_existing_fks(llm_candidates, fk_relationship_ids)

score_start = time.time()
logger.info("阶段5: 对候选关联进行评分")
scored_relations = self._score_candidates(filtered_candidates, tables)
```

修改后：
```python
logger.info("阶段4: 过滤已有物理外键（基于 relationship_id）")
filtered_candidates = self._filter_existing_fks(llm_candidates, fk_relationship_ids)

# 新增：阶段 4.5: 按语义角色过滤
logger.info("阶段4.5: 按语义角色过滤（exclude_semantic_roles）")
filtered_candidates = self._filter_by_semantic_roles(filtered_candidates, tables)

score_start = time.time()
logger.info("阶段5: 对候选关联进行评分")
scored_relations = self._score_candidates(filtered_candidates, tables)
```

**④ 与 rel 的一致性**：
- **过滤规则一致**：
  - 物理约束列不过滤
  - Complex 永远过滤（即使同名）
  - 同名列不过滤其他语义角色
  - 其他列按配置过滤
- **配置一致**：
  - 单列候选使用 `single_column.exclude_semantic_roles`
  - 复合候选使用 `composite.exclude_semantic_roles`
- **实现位置不同**：
  - `rel`：在候选生成阶段过滤（CandidateGenerator）
  - `rel_llm`：在 LLM 返回解析后、评分前过滤（LLMRelationshipDiscovery._finalize_relations）

### C. 逻辑主键推断的联动
**配置统一策略**：
本方案不在 `logical_key_detection` 下引入 `*_exclude_roles` 配置；逻辑主键检测统一复用：
- `single_column.exclude_semantic_roles`：单列逻辑主键排除列表
- `composite.exclude_semantic_roles`：复合逻辑主键排除列表

**代码改造要求**：
需要确保逻辑主键检测器确实使用了上述两处 exclude 列表（这是代码层面的改造点，不只是文档约定）：

- 文件：`metaweave/core/metadata/generator.py`
  - 位置：`MetadataGenerator._init_components()` 初始化 `LogicalKeyDetector` 之前
  - 修改内容：
    1. 从顶层配置读取 `single_column.exclude_semantic_roles` / `composite.exclude_semantic_roles`
    2. 将这两个值**注入（覆盖）**到 `logical_key_detection` 子配置中的 `single_column_exclude_roles` / `composite_exclude_roles`
    3. 再将完整的 `logical_key_detection` 配置传递给 `LogicalKeyDetector(config_dict)`

- 文件：`metaweave/core/metadata/logical_key_detector.py`
  - 位置：`LogicalKeyDetector.__init__(config_dict)` 内部（lines 44-52）
  - 修改内容：**无需修改构造函数签名**
  - 说明：仍从 `config_dict` 读取 `single_column_exclude_roles` / `composite_exclude_roles`，但这些值由 generator 注入，不再依赖 YAML 中的 `logical_key_detection.*_exclude_roles` 配置项

**实现后的效果**：
一旦 `complex` 被 profiler 正确识别，并加入上述 exclude 列表，逻辑主键推断会自然把这些列排除掉（无需额外配置）。

## 兼容性与风险
1. **识别不完整**：本阶段不引入 `udt_name`，因此对 `USER-DEFINED` 的复杂类型（如 PostGIS `geometry/geography`、range 类型）可能无法稳定识别为 `complex`。
2. **候选减少**：加入 complex 过滤后，关系候选数会减少，属于预期效果；但需要确保不会误伤"确实用于关联"的特殊场景（例如某些系统用 `jsonb` 存储外部 ID 并强制一致）。这种场景可以通过从 exclude 列表移除 `complex` 来放开（配置可控）。
3. **rel_llm 元数据依赖**：`rel_llm` 的语义角色过滤依赖完整的表元数据和列画像：
   - 如果目标表元数据缺失（`tables` 字典中无对应 key），候选会被提前过滤
   - 如果目标列画像缺失（`column_profiles` 中无对应列），候选会被丢弃（避免后续评分误判）
   - **排障提示**：如果 `rel_llm` 产出候选数异常偏少，检查上游元数据生成（`--step json`）是否完整，避免误以为"LLM 没返回候选"

## 验证与测试建议
### 单元测试（建议新增）
1. `MetadataProfiler`：
   - 输入 ColumnInfo `data_type=jsonb` → `semantic_role==complex`
   - 输入 ColumnInfo `data_type=ARRAY` → `semantic_role==complex`
2. `CandidateGenerator`：
   - 构造"非物理约束"的目标列 `semantic_role=complex`，且 `exclude_semantic_roles` 包含 `complex` → 该目标列不应产生候选（无论是否同名）
   - 构造"同名且非 complex"的目标列（如 `semantic_role=attribute`），且 `exclude_semantic_roles` 包含 `attribute` → 该目标列应产生候选（同名优先级高于其他语义角色过滤）
   - 构造"物理约束"的目标列 `semantic_role=complex` → 该目标列应产生候选（物理约束优先级最高）
3. `LogicalKeyDetector`：
   - 当 `single_column.exclude_semantic_roles` / `composite.exclude_semantic_roles` 包含 `complex` 时，complex 列不应被产出为逻辑主键候选。

### 集成验证（人工）
1. 运行 `--step json` 生成元数据，检查复杂类型列的 `semantic_role` 是否为 `complex`。
2. 运行 `--step rel` / `--step rel_llm`，比较改造前后的：
   - 候选数量（应下降）
   - 产出关系中是否仍含复杂类型列（应显著减少或为 0）
