# REL 复合键 Stage 1：索引与乱序子集匹配改造总结

## 背景
`--step rel` 在复合键（多列）候选生成的 Stage 1（特权模式）里，原先只允许：
- 目标表候选组合来自 PK/UK/UCCs（不含索引）
- 目标组合列数必须与源组合列数相等（不支持子集）
- 目标表的 UCCs 组合会按 `composite.exclude_semantic_roles` 做语义角色过滤

这会导致：
- 外键表存在多列索引（如 `(A,B,C)`）时，无法在 Stage 1 作为强信号参与匹配
- 驱动表组合 `(A,B)` 无法利用目标侧更长的组合（PK/UK/UCCs/索引）的任意 2 列子集进行匹配
- 外键表侧 UCCs 组合可能被语义角色过滤误杀

## 修改点（仅影响复合键 Stage 1）
### 1) 目标表 Stage 1 候选组合加入多列索引
- 在 Stage 1 目标侧候选池中，新增收集 `table_profile.indexes[*].columns`（2..max_columns）的组合。
- 索引不要求 `is_unique`。
- 注意：该改动仅用于目标侧 Stage 1 候选池，不改变源表组合收集逻辑。

涉及文件：
- `metaweave/core/relationships/candidate_generator.py`
  - 新增 `_collect_target_combinations_for_privilege_mode()`
  - Stage 1 改用该函数收集目标侧候选组合

### 2) 目标表侧 UCCs 组合不做语义角色过滤
- Stage 1 中目标侧（外键表侧）无论组合来源是 PK/UK/UCCs/索引，都视为特权候选，不做语义角色过滤。

涉及文件：
- `metaweave/core/relationships/candidate_generator.py`
  - `_find_target_columns()` Stage 1 调用 `_match_columns_as_set()` 时，目标侧统一 `target_is_physical=True`

### 3) Stage 1 支持“乱序子集匹配”（m > n）
- 允许源组合列数 `n` 小于目标组合列数 `m` 时进行匹配：
  - 先枚举目标组合的所有 n 列子集（C(m,n)）
  - 再对每个子集穷举排列（n!）
  - 使用现有的“逐对阈值淘汰 + best_score 选优”策略选择最佳匹配

涉及文件：
- `metaweave/core/relationships/candidate_generator.py`
  - `_match_columns_as_set()` 增加 `m > n` 的子集 + 排列逻辑
  - `_find_target_columns()` Stage 1 允许 `len(target_cols) >= len(source_cols)`

## 单元测试
新增用例覆盖：
- 目标侧多列索引 `(c,b,a)` 能匹配源 `(a,b)`（子集 + 乱序）
- 目标侧 PK `(c,b,a)` 能匹配源 `(a,b)`（子集 + 乱序，A 方案）
- 目标侧 UCCs 即使语义角色为 `metric` 也不被过滤，仍可完成 Stage 1 匹配

文件：
- `tests/unit/metaweave/test_candidate_generator_composite_stage1.py`

运行：
- `pytest -q tests/unit/metaweave/test_candidate_generator_composite_stage1.py`

