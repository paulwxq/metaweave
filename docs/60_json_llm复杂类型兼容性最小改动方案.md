# 60_json_llm 复杂类型兼容性修复方案

## 1. 背景

### 1.1 本次触发场景

在执行以下命令时：

```bash
python -m metaweave.cli.main pipeline generate --description "数据库中包含多个高速公路服务区的各种数据" --clean --regenerate-configs
```

`ddl` 和 `json_llm` 阶段针对 `public.highway_metadata` 出现了两类错误：

**错误 1：列统计失败（unhashable）**

```
ERROR - 获取列统计信息失败 (related_tables): unhashable type: 'list'
ERROR - 获取列统计信息失败 (questions): unhashable type: 'dict'
ERROR - 获取列统计信息失败 (keywords): unhashable type: 'list'
```

**错误 2：样例记录转换失败（ambiguous truth value）**

```
ERROR - 转换 DataFrame 为字典列表失败: The truth value of an array with more than one element is ambiguous.
```

该错误在 `ddl.log` 和 `json.log` 中均出现，影响 `ddl` 和 `json_llm` 两个步骤。

涉及的问题字段及其 PostgreSQL 类型：

| 字段 | PostgreSQL 类型 | psycopg3 Python 类型 | 触发的错误 |
|------|----------------|---------------------|-----------|
| `related_tables` | `ARRAY` | `list` | unhashable type: 'list' |
| `keywords` | `ARRAY` | `list` | unhashable type: 'list' |
| `questions` | `JSONB` | `dict`（或 `list`，取决于 JSON 根节点类型） | unhashable type: 'dict' |

> **驱动版本说明**：本项目使用 **psycopg3**（`import psycopg`，见 `metaweave/core/metadata/connector.py:9`），不是 psycopg2。  
> psycopg3 对 `JSON` 和 `JSONB` 类型均默认通过 `json.loads` 反序列化，返回 Python `dict` 或 `list`（取决于 JSON 根节点类型），**不会以字符串形式返回**。  
> 因此 `JSON` 和 `JSONB` 在本项目中具有完全相同的运行时行为，均需纳入复杂类型兼容处理。  
> 参考：[psycopg3 JSON adaptation 官方文档](https://www.psycopg.org/psycopg3/docs/basic/adapt.html#json-adaptation)

### 1.2 顺带修复的同类缺陷（BYTEA）

在历史日志（`08:20`、`16:29` 两次旧批次运行）中曾出现第三类错误：

**错误 3：bytea 字段统计失败（utf-8 decode）**

```
ERROR - 获取列统计信息失败 (picture): 'utf-8' codec can't decode byte 0x89 in position 0: invalid start byte
```

该错误来自另一个数据库（含 `BYTEA` 类型的 `picture` 列），当前 `highway_db` 不复现此问题。但 BYTEA 的根因与 ARRAY/JSONB 相同——`data_utils.py` 对复杂类型值缺乏兼容——且修复位置完全重叠，因此一并纳入本次修复，避免二次改动。

BYTEA 的修复属于"顺带修复同类缺陷"，不属于本次触发场景的必须验证项，详见第 10 节验证方案。

## 2. 目标

1. 修复 `ARRAY` / `JSON` / `JSONB` / `BYTEA` 字段在列统计和样例记录生成中的兼容性问题。
2. 不影响当前已经正常执行的标量类型处理逻辑（零回归）。
3. 不改变现有函数签名、调用链和输出文件的顶层结构。
4. 以最小改动完成修复，收敛在 `metaweave/utils/data_utils.py`。

## 3. 非目标

1. 不调整 `json_llm`、`ddl`、`pipeline generate` 的主流程。
2. 不改变 `sample_records` 顶层结构。
3. 不新增复杂类型专用的全新统计 schema。
4. 不改动已有正常标量列的统计口径。
5. 不引入新的配置项。

## 4. 问题根因

### 4.1 列统计逻辑问题（`get_column_statistics`）

`get_column_statistics()` 当前会对列值执行：

- `col_data.nunique()`
- `col_data.value_counts()`
- `calculate_uniqueness(df, [column])` → 内部同样调用 `data[col].nunique()`

这些操作要求值可哈希。当 Pandas 列中元素为 `list`（ARRAY）或 `dict`（JSONB）时，触发 `unhashable type` 异常。

此外，当 `col_data.dtype == object` 时，代码会执行字符串长度统计：

```python
non_null_data.astype(str).str.len()
```

ARRAY/JSONB/BYTEA 列的 dtype 同样是 `object`，会误入此分支。`astype(str)` 不会报错，但对 `list`/`dict` 算出的"字符串长度"是无意义的（等价于 `str([1,2,3])` 的长度）。

### 4.2 样例记录序列化问题（`dataframe_to_sample_dict`）

对每个值执行：

```python
if pd.isna(value):
```

当 `value` 为 list-like（如 `[1, 2, 3]`）时，`pd.isna(value)` 返回布尔数组，放入 `if` 判断触发：

```
The truth value of an array with more than one element is ambiguous.
```

当前异常处理是外层 `try/except`，一旦某个字段触发异常，**整张表所有行的样例全部丢失**（返回空列表），而不是仅跳过该字段。

### 4.3 bytea 字段统计问题

`bytes` 类型值在统计阶段被 Pandas 当作 `object` 处理，`astype(str)` 会调用 `bytes.__str__`，产生类似 `b'\x89PNG\r\n...'` 的字节串表示，但在某些路径上会尝试 UTF-8 解码，触发 `codec can't decode` 错误。

## 5. 设计原则

### 5.1 最小改动

仅在底层工具函数补齐复杂类型兼容，不修改上层流程编排。

### 5.2 标量逻辑零回归

对于以下常见类型，行为应保持与当前完全一致：

- `int`、`float`、`bool`
- `str`
- `datetime/date/time`
- `None / NaN / pd.NA`

### 5.3 输出契约

- `statistics` 顶层结构不变；`sample_count / null_count / null_rate` 对所有列均写入。  
  对 BYTEA 列，`unique_count / uniqueness / value_distribution` 不写入（跳过失真统计），下游应以 `.get(key, 默认值)` 方式读取，实际代码（`json_llm_enhancer.py:364`、`reader.py:316`）已全部使用此模式，运行时安全。
- `sample_records` 顶层结构保持不变
- 下游模块读取路径不变

### 5.4 错误隔离粒度

单字段序列化失败不能导致整行/整表样例丢失，错误应隔离在字段级别。

## 6. 修改范围

**生产代码仅修改以下一个文件**：

- `metaweave/utils/data_utils.py`

上层调用方不做流程改造，复用修复后的底层能力：

- `metaweave/core/metadata/generator.py`（无需改动）
- `metaweave/core/metadata/profiler.py`（无需改动）
- `metaweave/core/metadata/formatter.py`（无需改动）

**测试代码新增一个文件**（不影响生产范围评估）：

- `tests/unit/test_data_utils_complex_types.py`

测试文件与生产文件在评审和回归上独立管理，详见第 10.1 节。

## 7. 方案设计

### 7.1 新增内部辅助函数：复杂类型检测与标准化

在 `data_utils.py` 内新增以下内部辅助函数（以 `_` 开头，不对外暴露）。

**`_is_complex_value(value)`**：判断单个值是否为复杂类型。

```python
def _is_complex_value(value: Any) -> bool:
    return isinstance(value, (list, tuple, set, dict, bytes))
```

> 覆盖范围仅限 PostgreSQL 采样路径实际出现的 Python 类型（psycopg3 返回的 ARRAY → `list`、JSON/JSONB → `dict`/`list`、BYTEA → `bytes`，以及 Python 原生的 `tuple`/`set`）。不扩展到 `np.ndarray` 等非当前场景类型，避免引入不必要的副作用。

**`_normalize_for_hash(value)`**：将复杂值转换为可哈希的稳定字符串，用于 `nunique` / `value_counts`。

规则：

| 输入类型 | 处理方式 |
|---------|---------|
| `list / tuple / set` | `json.dumps(sorted(...), ensure_ascii=False)` 对可排序序列；否则 `str(value)` |
| `dict` | `json.dumps(value, ensure_ascii=False, sort_keys=True)` |
| `bytes` | 不参与哈希标准化（见 7.2 BYTEA 专项说明） |
| 其它（标量） | 原样返回，不做转换 |

> `dict` 使用 `sort_keys=True` 确保键顺序不影响哈希结果（见风险控制 11.1）。

### 7.2 修改 `get_column_statistics()`

保留函数签名与返回结构不变，只调整内部实现。

**步骤一：在函数入口检测列是否包含复杂类型，并区分 ARRAY/JSONB 与 BYTEA**

对全列非空值做类型扫描，只要任意一行包含复杂类型值即视为复杂类型列：

```python
non_null_values = col_data.dropna()
is_bytes_col   = any(isinstance(v, bytes) for v in non_null_values)
is_complex_col = (not is_bytes_col) and any(_is_complex_value(v) for v in non_null_values)
```

> **列类型一致性假设**：本方案默认同一列的非空值在数据库层面类型一致（PostgreSQL 强类型约束保证这一点）。若某列同时混有 `bytes` 和 `list/dict`，当前检测会将其整体归入 BYTEA 路径。这类混合列不作为支持目标，不在本方案的兼容范围内。

**为什么不能只看第一个非空值**：`object` 列中各行 Python 类型可以不一致，例如 ARRAY 列前几行可能是 `None`（数据库 NULL），通过 `dropna()` 后首行才是 `list`。若只取 `iloc[0]`，在首行恰好是标量的罕见情况下，`is_complex_col` 为 `False`，`nunique()` 仍会被调用并抛出 `unhashable` 错误，修复失效。全列扫描（`any()`）在样本量有限时（`sample_size` 默认 1000 行）开销可接受，且能确保检测不遗漏。

> **BYTEA 专项说明**：`bytes` 值若用固定占位 `"<binary>"` 标准化后参与 `nunique/value_counts`，会把所有非空二进制值压成同一个常量，导致 `unique_count` 恒为 1、`uniqueness` 被严重低估、`value_distribution` 完全失真。  
> 因此 BYTEA 列采取"**仅保留 sample_count/null_count/null_rate，跳过 unique_count/uniqueness/value_distribution**"的策略，返回有限但真实的统计，而不是失真的伪统计。

**步骤二：`unique_count` 和 `uniqueness`**

```python
if is_bytes_col:
    # BYTEA 跳过，不写入 unique_count / uniqueness
    pass
elif is_complex_col:
    hashable_series = col_data.dropna().apply(_normalize_for_hash)
    unique_count = int(hashable_series.nunique())
    uniqueness = round(unique_count / len(col_data), 4) if len(col_data) > 0 else 0.0
    stats["unique_count"] = unique_count
    stats["uniqueness"] = uniqueness
else:
    stats["unique_count"] = int(col_data.nunique())
    stats["uniqueness"] = float(calculate_uniqueness(df, [column]))
```

> 复杂类型（非 BYTEA）列不再调用 `calculate_uniqueness()`，避免该函数内部的 `nunique()` 再次触发 `unhashable` 错误。

**步骤三：`value_distribution` 同样基于标准化后的 Series 计算**

```python
if not is_bytes_col:  # BYTEA 跳过值分布
    effective_unique_count = stats.get("unique_count", 0)
    if effective_unique_count <= value_distribution_threshold:
        if is_complex_col:
            value_counts = hashable_series.value_counts().head(10)
        else:
            value_counts = col_data.value_counts().head(10)
        stats["value_distribution"] = {safe_str(k): int(v) for k, v in value_counts.items()}
```

**步骤四：字符串长度统计仅对"真字符串列"执行**

```python
is_string_col = (
    pd.api.types.is_string_dtype(col_data) or col_data.dtype == object
) and not is_complex_col and not is_bytes_col  # 排除 ARRAY/JSON/JSONB 和 BYTEA
```

只有 `is_string_col` 为 `True` 时才进入字符串长度统计分支。

> `is_bytes_col=True` 时 `is_complex_col` 为 `False`（两者互斥，见步骤一），因此必须**同时**排除两个标志，才能完整屏蔽 BYTEA 列进入此分支。

**步骤五：`null_count` 和 `null_rate` 对所有类型统一保留**

`isnull()` 对 `bytes` 和 `list/dict` 均能正常工作（返回 `False`），无需特殊处理，所有列均写入 `sample_count / null_count / null_rate`。

### 7.3 修改 `dataframe_to_sample_dict()` 的空值判断

将当前的直接 `pd.isna(value)` 替换为安全判断：

```python
def _is_null_value(value: Any) -> bool:
    """安全的空值判断，兼容复杂类型"""
    if value is None:
        return True
    if _is_complex_value(value):
        return False  # list/dict/bytes 不是空值，不走 pd.isna
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
```

### 7.4 修改 `dataframe_to_sample_dict()` 的错误隔离粒度

将异常处理细化到**字段级别**，单字段失败不影响其它字段和行：

```python
def dataframe_to_sample_dict(df, max_rows=5):
    if df.empty:
        return []
    sample_df = truncate_sample(df, max_rows)
    result = []
    for _, row in sample_df.iterrows():
        row_dict = {}
        for col in sample_df.columns:
            try:
                value = row[col]
                if _is_null_value(value):
                    row_dict[col] = None
                elif isinstance(value, bytes):
                    row_dict[col] = f"<binary:{len(value)} bytes>"
                elif isinstance(value, (list, dict)):
                    row_dict[col] = json.dumps(value, ensure_ascii=False, default=str)
                else:
                    row_dict[col] = safe_str(value, max_length=200)
            except Exception as e:
                logger.warning(f"字段序列化失败 ({col}): {e}")
                row_dict[col] = None
        result.append(row_dict)
    return result
```

关键改动：

1. 外层 `try/except` 移除，不再因一个字段失败返回整张表的空列表。
2. 内层每个字段独立 `try/except`，失败时该字段输出 `None`，继续处理其它字段。
3. `bytes` 输出 `"<binary:N bytes>"`（含实际字节长度），不尝试解码，同时保留长度信息。
4. `list/dict` 序列化为 JSON 字符串，保持"偏字符串化"的输出风格与下游兼容。

### 7.5 复杂类型处理规则汇总

| 场景 | ARRAY（list） | JSON/JSONB（dict/list） | BYTEA（bytes） | 标量 |
|------|--------------|------------------------|---------------|------|
| `sample_count` | 保留 | 保留 | 保留 | 保留 |
| `null_count / null_rate` | 保留 | 保留 | 保留 | 保留 |
| `unique_count / uniqueness` | 基于 JSON 字符串化后计算 | 基于 sort_keys JSON 字符串化后计算 | **跳过（不写入）** | 原逻辑不变 |
| `value_distribution` | 基于标准化值计算 | 基于标准化值计算 | **跳过（不写入）** | 原逻辑不变 |
| 字符串长度统计 | **跳过** | **跳过** | **跳过** | 原逻辑不变 |
| 数值统计 | 不触发（非数值类型）| 不触发 | 不触发 | 原逻辑不变 |
| 空值判断（`_is_null_value`） | 直接 `False` | 直接 `False` | 直接 `False` | `pd.isna()` |
| 样例序列化 | JSON 字符串 | JSON 字符串 | `"<binary:N bytes>"` | `safe_str()` |

> **BYTEA 样例输出**：`"<binary:N bytes>"` 含实际字节长度，不同行的 picture 字段若大小不同会显示不同占位，避免所有行看起来完全相同。

## 8. 兼容性分析

### 8.1 为什么不会影响当前正常逻辑

新分支仅在以下场景触发（通过 `_is_complex_value` 检测）：

- 值为 `list / tuple / set`（ARRAY）
- 值为 `dict` **或** `list`（JSON / JSONB，psycopg3 通过 `json.loads` 反序列化，根节点为对象时返回 `dict`，根节点为数组时返回 `list`）
- 值为 `bytes`（BYTEA）

对于普通标量列：

- 统计逻辑仍按原路径计算（`nunique`、`value_counts`、字符串长度统计）
- 样例记录仍按原方式序列化（`safe_str`）
- 不改变字段名、结构、调用入口

### 8.2 `JSON` 与 `JSONB` 行为一致，均需兼容处理

psycopg3（本项目使用的驱动）对 `JSON` 和 `JSONB` 均默认调用 `json.loads` 反序列化，返回 Python `dict` 或 `list`。两者在运行时行为完全相同，均会触发 `unhashable type` 错误。

因此本方案对 `JSON` 和 `JSONB` 采用同一套处理逻辑，无需区分。

### 8.3 为什么收敛在 `data_utils.py`

如果把兼容处理散落到 `generator`、`formatter`、`profiler` 多处：

- 风险面更大，回归范围更大
- 容易出现重复修补但行为不一致

本问题本质上属于底层数据值兼容问题，收敛在 `data_utils.py` 最合理。

## 9. 预期收益

修复后：

1. `related_tables / questions / keywords` 不再报错，`statistics` 不再是空字典，改为返回有限但真实的统计字段（`sample_count / null_count / null_rate / unique_count / uniqueness`，唯一值较少时还包含 `value_distribution`）。
2. `sample_records.records` 可正常落盘，DDL 中可重新生成 `SAMPLE_RECORDS` 注释块。
3. `picture`（BYTEA）不再出现 UTF-8 解码错误，统计只保留 `sample_count/null_count/null_rate`（跳过分布统计），样例中输出 `"<binary:N bytes>"`。
4. 单字段序列化失败不再导致整张表样例丢失。
5. 现有其它正常表（`bss_service_area`、`bss_branch`、`qa_feedback` 等）的输出保持不变。

## 10. 验证方案

### 10.1 单元验证

新增测试文件 `tests/unit/test_data_utils_complex_types.py`，覆盖以下场景：

| 场景 | 验证点 | 优先级 |
|------|-------|-------|
| 标量列统计 | `unique_count / null_rate / value_distribution` 与修改前一致 | 必须 |
| ARRAY（list）列 | 可计算 `unique_count / null_rate`，不报错 | 必须 |
| JSON/JSONB（dict/list）列 | 可计算 `unique_count / null_rate`，不报错；dict 根节点和 list 根节点均覆盖；低基数场景下还应覆盖 `value_distribution` | 必须 |
| 混合列（前几行为标量、后续行为 list） | 全列扫描检测到复杂类型，走标准化路径，不报错 | 必须 |
| `dataframe_to_sample_dict` 含 list/dict | 不抛异常，序列化为 JSON 字符串 | 必须 |
| 单字段失败 | 该字段为 `None`，其它字段正常，不影响其它行 | 必须 |
| BYTEA（bytes）列统计 | 不触发 utf-8 decode 错误，只有 sample_count/null_count/null_rate，无 unique_count | 选做 |
| `dataframe_to_sample_dict` 含 bytes | 不抛异常，输出 `"<binary:N bytes>"` 格式 | 选做 |

### 10.2 回归验证（本次触发场景）

重新执行：

```bash
python -m metaweave.cli.main pipeline generate \
  --description "数据库中包含多个高速公路服务区的各种数据" \
  --clean --regenerate-configs
```

重点验证（必须通过）：

1. `logs/ddl.log` 中不再出现 `转换 DataFrame 为字典列表失败`
2. `logs/json.log` 中不再出现 `unhashable type: 'list'`
3. `logs/json.log` 中不再出现 `unhashable type: 'dict'`
4. `output/json/highway_db.public.highway_metadata.json` 中：
   - `sample_records.records` 非空
   - `related_tables / questions / keywords` 的 `statistics` 非空

BYTEA 相关验证（`utf-8 codec can't decode`）不在本次回归必须项内，待有 BYTEA 列的数据库接入时再做专项验证。

### 10.3 稳定性验证

对其它本来正常的表进行抽样比对：

- `bss_service_area`
- `bss_branch`
- `qa_feedback`

验证其 `sample_records` 结构未变化，标量字段统计结果无异常波动。

## 11. 风险与控制

### 11.1 风险

| 风险 | 说明 |
|------|------|
| dict 键顺序 | 不同 Python 版本下 dict 遍历顺序理论上一致（3.7+），但保险起见用 `sort_keys=True` |
| list 元素不可排序 | 混合类型 list（如 `[1, "a"]`）无法 `sorted()`，回退到 `str(value)` |
| JSON 序列化失败 | 嵌套对象含不可序列化类型时，`json.dumps` 失败，需 `default=str` 兜底 |
| BYTEA 统计字段缺失 | BYTEA 列的 `unique_count/uniqueness/value_distribution` 不写入，下游读取时需容忍字段缺失 |

### 11.2 控制措施

1. `dict` 序列化使用 `sort_keys=True` 保证稳定性。
2. `list` 排序失败时回退到 `str(value)`，不中断流程。
3. `json.dumps` 使用 `default=str` 兜底，避免不可序列化类型引发新异常。
4. BYTEA 列主动跳过会失真的统计字段，而非用固定占位伪造数据，保证"有限但真实"原则。
5. 所有复杂类型分支均有独立异常捕获，失败输出占位值，不向上抛出。

## 12. 结论

本问题的本质不是表级流程失败，而是底层工具函数对复杂类型值（ARRAY/JSON/JSONB/BYTEA）缺乏兼容。

采用"最小改动、底层收敛、输出契约不变、错误字段级隔离"的方案：

1. **生产代码仅修改 `metaweave/utils/data_utils.py`**，不改主流程；另补 `tests/unit/test_data_utils_complex_types.py` 覆盖新增逻辑。
2. 新增 `_is_complex_value`、`_normalize_for_hash`、`_is_null_value` 三个内部辅助函数。
3. `get_column_statistics()` 区分三种路径：标量（原逻辑）、ARRAY/JSON/JSONB（标准化后计算）、BYTEA（跳过分布统计，仅保留 sample_count/null_count/null_rate）。字符串长度统计排除所有复杂类型列。
4. `dataframe_to_sample_dict()` 替换空值判断为 `_is_null_value()`，将错误隔离粒度从"整张表"细化到"单字段"。BYTEA 列样例输出 `"<binary:N bytes>"`（含长度），JSON/JSONB/ARRAY 列序列化为 JSON 字符串。
5. `JSON` 和 `JSONB` 在 psycopg3 下行为一致（均返回 dict/list），统一处理，不再区分。
