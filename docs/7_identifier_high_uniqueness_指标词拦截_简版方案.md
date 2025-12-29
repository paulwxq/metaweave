# identifier 规则2（high_uniqueness）“指标词拦截”简版改造方案

**状态（当前不做 / 已知问题）**：
- 当前代码未实现 `sampling.identifier_detection.high_uniqueness_block_keywords` 的读取与拦截逻辑。
- 因此在 `tests/unit/metaweave/test_profiler.py` 的场景里，`amount` 仍会因 `high_uniqueness` 被判为 `identifier`（而非 `metric`）。

## 目标

修复：无小数数值型指标列（如 `amount numeric` / `amount integer`）因为样本高唯一性而被 `_is_identifier()` 直接判为 `identifier`，从而抢占 `metric` 分支的问题。

## 改造范围

仅改动 identifier 判断逻辑中的 **规则2：high_uniqueness**；不调整整体语义角色优先级，不改 metric 规则本身。

## 改造点（代码）

### 1) 在 `_is_identifier()` 的规则2返回前增加拦截

文件：`metaweave/core/metadata/profiler.py`  
函数：`MetadataProfiler._is_identifier(...)`

现状（关键点）：
- 规则2 `high_uniqueness` 命中后直接 `return True`（判为 identifier），不会进入后续命名规则/metric 分支。

改造：
- 在准备因为 `high_uniqueness` 返回 identifier 之前，加入 "指标词拦截"：
  - **仅对无小数的数值型生效**（integer/bigint/smallint + numeric/decimal 且 `scale=0`）
  - **仅影响规则2（high_uniqueness）**：拦截后跳过“规则2直接返回 True”，继续走规则3；若规则3也不命中，则最终返回 False（让后续 metric 分支处理）

伪代码（定位清晰，便于落地）：
```python
# 规则2：统计高唯一性（逻辑推断）
has_high_uniq, uniq_conf, uniq_reason = self._has_high_uniqueness(stats)
if has_high_uniq:
    # ===== 指标词拦截（仅阻止 high_uniqueness 直接判 id）=====
    if self._should_block_high_uniqueness_identifier(column):
        # 不允许仅凭 high_uniqueness 判为 identifier：跳过规则2的直接返回，继续走规则3
        # 说明：blocked reason 仅用于日志（logger.debug），不作为返回值输出
        # logger.debug("identifier high_uniqueness blocked by metric keyword: %s", column.column_name)
        pass
    # ==========================================================
    inference_basis.append(uniq_reason)
    return (True, uniq_conf, "logical_primary_key", inference_basis)
```

### 2) 新增 `_should_block_high_uniqueness_identifier()`（建议）

文件：`metaweave/core/metadata/profiler.py`  
新增方法（示例签名）：
```python
def _should_block_high_uniqueness_identifier(self, column: ColumnInfo) -> bool:
    ...
```

判定逻辑（必须具备的技术细节）：
- 类型条件：无小数的数值型（integer/bigint/smallint + numeric/decimal 且 `scale=0`）
- 名称条件：`column.column_name.lower()` 命中配置的指标关键词（见下节配置）
- 物理约束豁免：如果列有物理约束（PK/FK/UNIQUE constraint 等）则返回 False（不拦截）

实现注意（不要漏）：
- `high_uniqueness_block_keywords` 需要被 `ProfilingConfig.from_dict()` 读取并缓存（例如 `self.config.high_uniqueness_block_keywords`），否则仅改 YAML 无效。
- 简版方案不把 blocked reason 作为 `_is_identifier()` 的返回值输出；blocked 只在函数内部 `logger.debug` 记录，不进入 JSON。
  - 若必须落到 JSON：需要额外设计“把 blocked reason 合并进 inference_basis（或单独字段）”的落地方式。

关键词匹配规则（必须写清楚，避免实现偏差）：
- 匹配方式：大小写不敏感（统一对 `column_name` 与关键词做 `lower()`）。
- 建议采用“token 匹配”而非纯子串匹配：
  - 将列名按 `_` 和非字母数字分隔符切分为 tokens（例如 `total_amount_id` → `["total", "amount", "id"]`）
  - 规则：只要任一 token 等于 `high_uniqueness_block_keywords` 中的某个关键词，即视为命中
  - 目的：避免误伤，例如 `account_id` 不应因包含子串 `count` 而命中 `count`
- 示例：
  - `amount`：tokens=`["amount"]`，命中 `amount` → 触发拦截（仅阻止规则2 high_uniqueness 的直接返回）
  - `total_amount_id`：tokens=`["total","amount","id"]`，命中 `amount` → 会跳过规则2，但仍会继续走规则3（通常会被识别为 identifier）

## 配置（YAML）

新增配置项：`sampling.identifier_detection.high_uniqueness_block_keywords`

注意：
- 当前代码已支持并正在读取 `sampling.identifier_detection.allowed_data_types / high_uniqueness_threshold / min_non_null_rate / low_uniqueness_threshold / exclude_keywords`。
- 本方案新增的是 **“仅阻止规则2（high_uniqueness）直接判 identifier”** 的关键词列表，**不要**把 `amount/count/...` 这类指标词塞进 `exclude_keywords`：
  - `exclude_keywords` 属于规则0a“强排除”，发生在物理约束检查之前，会把 `amount_id` 这类字段也一并排除掉（即使它有 FK/PK/UNIQUE constraint）。

```yaml
sampling:
  identifier_detection:
    # 已存在：数据类型白名单（identifier 前置过滤）
    allowed_data_types: [...]
    # 已存在：规则2/规则3阈值
    high_uniqueness_threshold: 0.95
    min_non_null_rate: 0.80
    low_uniqueness_threshold: 0.05
    # 已存在：规则0a 强排除（描述性字段）
    exclude_keywords: [name, desc, ...]

    # 当列"整数类型 + 命中指标关键词"时，阻止其因 high_uniqueness 被直接判为 identifier
    high_uniqueness_block_keywords:
      - amount
      - count
      - total
      - sum
      - cost
      - price
      - revenue
      - sales
      - profit
      - qty
      - quantity
      - rate
      - ratio
      - percent
```

说明：
- 该配置 **只影响 `_is_identifier()` 的规则2（high_uniqueness）**，不改变规则1（物理约束）与规则3（命名特征）。

## 验收（必须）

- `tests/unit/metaweave/test_profiler.py`：`amount` 最终应判为 `metric`（不再被 high_uniqueness 抢占为 identifier）
- 回归检查（最小集合）：
  - `*_id` / `*_no` / `*_code` 等命名强特征列仍可判为 identifier（规则3）
  - 有 PK/FK/UNIQUE constraint 的列不受拦截影响（规则1）
