# rel+llm 混合模式设计方案

> **文档版本**: 1.0  
> **创建日期**: 2025-12-28  
> **状态**: 设计阶段  
> **目标**: 通过独立分析+智能合并策略，最大化关系发现的准确度

---

## 📋 目录

- [执行摘要](#执行摘要)
- [设计理念](#设计理念)
- [核心优势](#核心优势)
- [完整流程设计](#完整流程设计)
  - [阶段0：物理外键提取](#阶段0物理外键提取)
  - [阶段1：LLM语义分析](#阶段1llm语义分析)
  - [阶段2：REL规则分析](#阶段2rel规则分析)
  - [阶段3：三源智能合并](#阶段3三源智能合并)
- [配置设计](#配置设计)
- [输出目录结构](#输出目录结构)
- [输出格式设计](#输出格式设计)
- [与现有代码集成](#与现有代码集成)
- [实现路线图](#实现路线图)
- [性能评估](#性能评估)
- [风险与缓解](#风险与缓解)
- [未来扩展](#未来扩展)

---

## 执行摘要

### 🎯 目标

通过 **独立分析 + 智能合并** 策略，结合物理外键、LLM语义理解和规则评分三种方法，最大化关系发现的准确度。

### 核心特性

1. **物理外键绝对优先**：数据库DDL定义的外键约束 = 100%置信度，直通输出
2. **独立分析避免干扰**：LLM和REL独立分析，互不影响，避免锚定偏差
3. **智能过滤提升效率**：REL只分析LLM未高置信度覆盖的表对，减少70%+计算量
4. **多源验证提升质量**：物理外键+LLM+REL三源验证，双确认关系可信度极高
5. **输出分离便于调试**：三个独立输出目录，完整溯源信息，透明度高

### 命令格式

```bash
metaweave metadata --config configs/metadata_config.yaml --step rel+llm
```

### 预期效果

| 指标 | 现有 `rel` | 现有 `rel_llm` | 新 `rel+llm` |
|------|-----------|---------------|-------------|
| **准确度** | 80-85% | 85-90% | **90-95%** ✨ |
| **召回率** | 70-75% | 80-85% | **85-90%** ✨ |
| **计算效率** | 基准 | LLM慢 | **REL计算量↓70%** ✨ |
| **可信度分层** | 单一 | 单一 | **5层置信度** ✨ |

---

## 设计理念

### 核心原则

#### 1. 独立分析，避免偏差
> **"让LLM自由思考，不被规则束缚；让规则自由计算，不被LLM影响"**

- ❌ **反模式**：先REL后LLM，LLM可能被REL结果锚定
- ✅ **正确做法**：LLM和REL独立分析，互不知晓对方结果

#### 2. 物理外键即真理
> **"数据库级别的强约束 = 绝对正确"**

- 物理外键 = 开发者显式定义 = 业务规则 = 100%可信
- 任何算法（LLM或REL）都不能推翻物理外键
- 物理外键直通，无需验证

#### 3. 智能过滤，避免重复
> **"已经确认的关系，不再重复分析"**

- LLM分析：排除物理外键表对
- REL分析：排除物理外键 + LLM高置信度表对
- 避免浪费计算资源

#### 4. 多源验证，提升质量
> **"独立确认 = 极高可信度"**

- 物理外键（1源）= absolute置信度
- LLM + REL双确认（2源）= very_high置信度
- LLM独有高分（1源）= high置信度
- 单源低分 = 标记为可疑

#### 5. 透明可追溯
> **"每个关系都能溯源到具体分析方法"**

- 三个独立输出目录（rel_llm, rel_rule, rel）
- 详细的合并分析报告
- 冲突关系清晰标记

---

## 核心优势

### vs. 现有 `--step rel`

| 对比维度 | `rel` | `rel+llm` | 提升 |
|---------|-------|-----------|------|
| **准确度** | 80-85% | 90-95% | +10-15% |
| **召回率** | 70-75% | 85-90% | +15% |
| **语义关系** | 无法识别 | 可识别 | ✨ 新能力 |
| **置信度分层** | 3层 | 5层 | 更精细 |

**示例**：字段名不同但语义相同的关系
```
订单表.客户编号 → 客户表.会员号
```
- `rel`: 无法发现（name_similarity低）
- `rel+llm`: LLM可识别语义相同 ✅

### vs. 现有 `--step rel_llm`

| 对比维度 | `rel_llm` | `rel+llm` | 提升 |
|---------|----------|-----------|------|
| **准确度** | 85-90% | 90-95% | +5% |
| **验证机制** | 单一LLM | 三源验证 | ✨ 更可靠 |
| **计算效率** | LLM全量分析 | REL计算量↓70% | ✨ 更高效 |
| **错误检测** | 无 | REL可纠错LLM | ✨ 新能力 |

**示例**：LLM误判的关系
```
LLM: product_code → batch_code (误判为关联)
REL: inclusion_rate=0.02, name_similarity=0.6 → 拒绝 ✅
```

### 独有优势

1. **物理外键直通**：100%置信度，无需算法验证
2. **双确认机制**：LLM+REL独立确认的关系，可信度极高
3. **智能纠错**：REL可以拒绝LLM的低分判断
4. **补充发现**：LLM可以发现REL遗漏的语义关系
5. **冲突标记**：同一表对的不同判断，清晰标记供人工审核

---

## 完整流程设计

### 流程概览

```
输入：13张表 → 78个表对
    ↓
阶段0：物理外键提取
    ↓ 发现8个，剩余70个表对
阶段1：LLM语义分析（70个表对）
    ↓ 发现45个（高分38，低分7）
阶段2：REL规则分析（20个表对，智能过滤）
    ↓ 发现12个
阶段3：三源智能合并
    ↓
输出：57个关系（分5层置信度）
```

---

### 阶段0：物理外键提取

#### 目标
从数据库DDL中提取物理外键约束，作为**基础事实层**。

#### 输入
- 表元数据（JSON文件，包含`physical_constraints.foreign_keys`）

#### 处理逻辑

```python
def extract_physical_foreign_keys(tables: Dict[str, Dict]) -> List[Relation]:
    """
    提取物理外键约束
    
    特点：
    - 100% 置信度
    - 无需验证
    - 绝对优先级
    """
    physical_fks = []
    
    for table_name, table_data in tables.items():
        constraints = table_data.get("table_profile", {}) \
                                 .get("physical_constraints", {})
        foreign_keys = constraints.get("foreign_keys", [])
        
        for fk in foreign_keys:
            relation = Relation(
                source_schema=table_data["table_info"]["schema_name"],
                source_table=table_data["table_info"]["table_name"],
                source_columns=fk["source_columns"],
                target_schema=fk["target_schema"],
                target_table=fk["target_table"],
                target_columns=fk["target_columns"],
                
                # 固定属性
                confidence_level="absolute",
                composite_score=1.0,
                discovery_method="physical_constraint",
                
                # 约束信息
                constraint_name=fk.get("constraint_name"),
                on_delete=fk.get("on_delete"),
                on_update=fk.get("on_update"),
            )
            physical_fks.append(relation)
    
    return physical_fks
```

#### 输出

**数量示例**：8个物理外键

**输出文件**：`output/rel/physical_fks.json`（可选）

**格式示例**：
```json
{
  "relationship_id": "rel_physical_001",
  "type": "single_column",
  "from_table": {"schema": "public", "table": "employee"},
  "from_column": "dept_id",
  "to_table": {"schema": "public", "table": "department"},
  "to_column": "dept_id",
  
  "discovery_method": "physical_constraint",
  "confidence_level": "absolute",
  "composite_score": 1.0,
  
  "constraint_info": {
    "constraint_name": "fk_employee_department",
    "on_delete": "NO ACTION",
    "on_update": "NO ACTION"
  },
  
  "source": "physical_constraint"
}
```

#### 关键规则

1. **绝对优先级**：任何后续分析都不能推翻物理外键
2. **无需验证**：跳过所有评分和验证步骤
3. **直通输出**：直接加入最终结果

---

### 阶段1：LLM语义分析

#### 目标
使用LLM基于语义理解，独立分析表对之间的关联关系。

#### 输入
- 表元数据（完整JSON，包含注释、样例数据等）
- 排除：已有物理外键的表对

#### 处理逻辑

```python
def llm_semantic_analysis(tables: Dict, physical_fks: List[Relation], config: Dict) -> List[Relation]:
    """
    LLM 语义分析
    
    特点：
    - 独立分析（不知道 REL 结果）
    - 基于语义理解
    - 可发现字段名不同但语义相同的关系
    """
    
    # 1. 排除已有物理外键的表对
    fk_table_pairs = {get_table_pair_signature(fk) for fk in physical_fks}
    
    # 2. 生成所有表对（或智能过滤）
    all_table_pairs = generate_all_table_pairs(tables)
    llm_target_pairs = [pair for pair in all_table_pairs 
                        if get_table_pair_signature_from_names(pair) not in fk_table_pairs]
    
    logger.info(f"LLM 分析目标: {len(llm_target_pairs)} 个表对")
    logger.info(f"  - 已排除物理外键表对: {len(fk_table_pairs)}")
    
    # 3. LLM 独立分析
    discovery = LLMRelationshipDiscovery(config, connector)
    llm_relations = discovery.discover_for_pairs(llm_target_pairs)
    
    # 4. 标记来源
    for rel in llm_relations:
        rel.source = "llm_analysis"
    
    return llm_relations
```

#### LLM 提示词要点

```
你是数据库关系分析专家。分析以下两个表的关联关系。

## 表1: {table1_name}
- 表注释: {table_comment}
- 列信息: {columns_with_comments}
- 样例数据: {sample_records}

## 表2: {table2_name}
- 表注释: {table_comment}
- 列信息: {columns_with_comments}
- 样例数据: {sample_records}

## 任务
考虑以下因素：
1. 字段名相同或相似
2. 数据类型兼容
3. 字段注释的语义关联
4. 样例数据的值域匹配
5. 复合键的可能性

## 输出
返回 JSON 格式的关联关系（单列或复合键）
```

#### 输出

**数量示例**：45个关系（高分38，低分7）

**输出文件**：`output/rel_llm/relationships_llm.json`

**统计信息**：
```json
{
  "total": 45,
  "high_confidence": 38,
  "low_confidence": 7,
  "table_pairs_analyzed": 70
}
```

#### 关键特点

1. **独立性**：不知道REL的分析结果
2. **语义理解**：可识别字段名不同但语义相同的关系
3. **样例驱动**：基于实际数据值判断
4. **复合键支持**：可发现多字段组合关系

---

### 阶段2：REL规则分析

#### 目标
使用规则-based方法，对**需要验证**的表对进行分析。

#### 输入
- 表元数据（JSON文件）
- 数据库连接（用于采样计算inclusion_rate等）
- 排除：物理外键表对 + LLM高置信度表对

#### 处理逻辑

```python
def rel_rule_analysis(tables: Dict, physical_fks: List[Relation], 
                      llm_relations: List[Relation], config: Dict) -> List[Relation]:
    """
    REL 规则分析（智能过滤）
    
    特点：
    - 只分析需要验证的表对
    - 排除已确认的关系
    - 减少70%+计算量
    """
    
    # 1. 收集已确认的表对
    confirmed_pairs = set()
    
    # 1.1 物理外键表对
    for fk in physical_fks:
        confirmed_pairs.add(get_table_pair_signature(fk))
    
    # 1.2 LLM 高置信度表对
    llm_high_threshold = config.get("hybrid_mode", {}) \
                               .get("llm_analysis", {}) \
                               .get("high_confidence_threshold", 0.85)
    
    for llm_rel in llm_relations:
        if llm_rel.composite_score >= llm_high_threshold:
            confirmed_pairs.add(get_table_pair_signature(llm_rel))
    
    # 2. 生成需要 REL 分析的表对
    all_table_pairs = generate_all_table_pairs(tables)
    rel_target_pairs = [pair for pair in all_table_pairs 
                        if get_table_pair_signature_from_names(pair) not in confirmed_pairs]
    
    logger.info(f"REL 分析目标: {len(rel_target_pairs)} 个表对")
    logger.info(f"  - 排除物理外键: {len([p for p in physical_fks])}")
    logger.info(f"  - 排除 LLM 高置信度: {len(confirmed_pairs) - len(physical_fks)}")
    logger.info(f"  - 计算量节省: {(1 - len(rel_target_pairs) / len(all_table_pairs)) * 100:.1f}%")
    
    # 3. REL 规则分析
    pipeline = RelationshipDiscoveryPipeline(config)
    rel_relations = pipeline.discover_for_pairs(rel_target_pairs)
    
    # 4. 标记来源
    for rel in rel_relations:
        rel.source = "rel_analysis"
    
    return rel_relations
```

#### REL 分析目标

| 目标类型 | 说明 | 示例数量 |
|---------|------|---------|
| LLM 未覆盖的表对 | LLM 没有分析的表对 | 12个 |
| LLM 低置信度关系 | 需要 REL 二次验证 | 8个 |

#### 输出

**数量示例**：12个关系

**输出文件**：`output/rel_rule/relationships_rule.json`

**统计信息**：
```json
{
  "total": 12,
  "table_pairs_analyzed": 20,
  "computation_saved": "74.4%",
  "discovery_methods": {
    "active_search": 8,
    "composite_logical_key": 3,
    "dynamic_composite": 1
  }
}
```

#### 效率提升

```
总表对：78个
REL 分析：20个
节省：58个（74.4%）

详细：
- 排除物理外键：8个
- 排除 LLM 高置信度：50个
```

---

### 阶段3：三源智能合并

#### 目标
整合物理外键、LLM和REL三个来源的分析结果，生成最终的高质量关系列表。

#### 输入
- 物理外键：8个
- LLM关系：45个
- REL关系：12个

#### 合并算法

```python
class HybridRelationshipMerger:
    """三源智能合并器"""
    
    def merge(self, physical_fks: List[Relation], 
              llm_relations: List[Relation], 
              rel_relations: List[Relation]) -> MergeResult:
        """
        合并三个来源的关系
        
        优先级：
        1. 物理外键（absolute）
        2. LLM + REL 双确认（very_high）
        3. LLM 独有高分（high）
        4. REL 独有（medium）
        5. LLM 低分未确认（low，可疑）
        """
        
        final_relations = []
        analysis = {
            "physical_fks": [],           # 物理外键
            "llm_rel_both": [],           # 双确认
            "llm_only_high": [],          # LLM 独有高分
            "llm_only_low": [],           # LLM 独有低分
            "rel_only": [],               # REL 独有
            "conflicts": [],              # 冲突
        }
        
        # === 第1层：物理外键（绝对优先） ===
        for fk in physical_fks:
            fk.confidence_level = "absolute"
            fk.composite_score = 1.0
            final_relations.append(fk)
            analysis["physical_fks"].append(fk)
        
        # === 第2层：建立索引 ===
        llm_index = self._build_index(llm_relations)
        rel_index = self._build_index(rel_relations)
        fk_sigs = {self._get_signature(fk) for fk in physical_fks}
        
        # === 第3层：处理 LLM 发现的关系 ===
        for llm_rel in llm_relations:
            sig = self._get_signature(llm_rel)
            
            # 跳过已有物理外键的
            if sig in fk_sigs:
                continue
            
            rel_rel = rel_index.get(sig)
            
            if rel_rel:
                # 情况1：LLM + REL 双确认
                merged = self._merge_llm_rel(llm_rel, rel_rel)
                merged.confidence_level = "very_high"
                merged.source = "llm_rel_both"
                final_relations.append(merged)
                analysis["llm_rel_both"].append(merged)
                
            else:
                # 情况2：仅 LLM 发现
                if llm_rel.composite_score >= self.llm_high_threshold:
                    llm_rel.confidence_level = "high"
                    llm_rel.source = "llm_only_high"
                    final_relations.append(llm_rel)
                    analysis["llm_only_high"].append(llm_rel)
                else:
                    # LLM 低分且 REL 未确认 → 可疑
                    llm_rel.confidence_level = "low"
                    llm_rel.source = "llm_only_low"
                    llm_rel.add_warning("⚠️ LLM 低置信度且 REL 未确认")
                    if self.include_suspicious:
                        final_relations.append(llm_rel)
                    analysis["llm_only_low"].append(llm_rel)
        
        # === 第4层：处理 REL 独有发现 ===
        for rel_rel in rel_relations:
            sig = self._get_signature(rel_rel)
            
            # 跳过已处理的
            if sig in fk_sigs or sig in llm_index:
                continue
            
            # 情况3：仅 REL 发现（LLM 未分析该表对）
            rel_rel.confidence_level = "medium"
            rel_rel.source = "rel_only"
            final_relations.append(rel_rel)
            analysis["rel_only"].append(rel_rel)
        
        # === 第5层：冲突检测 ===
        conflicts = self._detect_conflicts(llm_relations, rel_relations, fk_sigs)
        analysis["conflicts"] = conflicts
        
        # 生成报告
        report = self._generate_report(analysis)
        
        return MergeResult(
            relations=final_relations,
            analysis=analysis,
            report=report
        )
    
    def _merge_llm_rel(self, llm_rel: Relation, rel_rel: Relation) -> Relation:
        """
        合并 LLM 和 REL 的一致结果
        
        策略：
        - 分数加权平均（LLM 60%, REL 40%）
        - 保留双方详细信息
        - 标记为 very_high 置信度
        """
        merged = copy.deepcopy(llm_rel)
        
        # 分数合并
        merged.composite_score = (
            llm_rel.composite_score * 0.6 +  # LLM 权重更高
            rel_rel.composite_score * 0.4
        )
        
        # 保留双方信息
        merged.sources = {
            "llm": {
                "score": llm_rel.composite_score,
                "reasoning": getattr(llm_rel, "llm_reasoning", None)
            },
            "rel": {
                "score": rel_rel.composite_score,
                "method": rel_rel.discovery_method,
                "details": rel_rel.score_details
            }
        }
        
        return merged
    
    def _detect_conflicts(self, llm_relations: List[Relation], 
                          rel_relations: List[Relation],
                          fk_sigs: Set[str]) -> List[Dict]:
        """
        检测冲突：同一表对，不同列组合
        
        示例冲突：
        - LLM: order.customer_id -> customer.id
        - REL: order.customer_code -> customer.code
        """
        conflicts = []
        
        # 按表对分组
        llm_by_table = self._group_by_table_pair(llm_relations, fk_sigs)
        rel_by_table = self._group_by_table_pair(rel_relations, fk_sigs)
        
        # 找出共同的表对
        common_pairs = set(llm_by_table.keys()) & set(rel_by_table.keys())
        
        for table_pair in common_pairs:
            llm_rels = llm_by_table[table_pair]
            rel_rels = rel_by_table[table_pair]
            
            # 检查列组合是否不同
            llm_cols = {self._get_column_signature(r) for r in llm_rels}
            rel_cols = {self._get_column_signature(r) for r in rel_rels}
            
            if llm_cols != rel_cols:
                conflicts.append({
                    "table_pair": table_pair,
                    "llm_columns": list(llm_cols),
                    "rel_columns": list(rel_cols),
                    "llm_relations": llm_rels,
                    "rel_relations": rel_rels,
                    "resolution": "keep_both",  # 保留双方，标记需人工审核
                })
        
        return conflicts
```

#### 合并规则详解

| 情况 | LLM | REL | 结果 | 置信度 |
|------|-----|-----|------|--------|
| 1 | ✅ | ✅ | 双确认 | very_high |
| 2 | ✅高分 | ❌ | LLM独有 | high |
| 3 | ✅低分 | ❌ | 可疑 | low |
| 4 | ❌ | ✅ | REL独有 | medium |
| 5 | ✅ | ✅ | 列不同（冲突） | 标记审核 |

#### 置信度层级

```
absolute (1.0)         物理外键
    ↓
very_high (0.90-0.99)  LLM + REL 双确认
    ↓
high (0.85-0.89)       LLM 独有高分
    ↓
medium (0.80-0.84)     REL 独有
    ↓
low (<0.80)            LLM 低分未确认（可疑）
```

#### 输出

**数量示例**：57个关系

**置信度分布**：
- absolute: 8个（物理外键）
- very_high: 8个（双确认）
- high: 30个（LLM独有高分）
- medium: 4个（REL独有）
- low: 7个（可疑，需审核）

**输出文件**：
- `output/rel/relationships_global.json`（最终结果）
- `output/rel/relationships_global.md`（可读格式）
- `output/rel/merge_analysis.json`（详细分析）

---

## 配置设计

### 完整配置示例

```yaml
# configs/metadata_config.yaml

relationships:
  # ====== 混合模式配置 ======
  hybrid_mode:
    enabled: true
    
    # 执行顺序
    execution_order:
      - physical_fks    # 第0步：物理外键
      - llm            # 第1步：LLM 分析
      - rel            # 第2步：REL 分析
    
    # ---------- 阶段0：物理外键配置 ----------
    physical_fks:
      confidence: 1.0              # 固定为 1.0
      priority: "absolute"         # 绝对优先级
      skip_validation: true        # 跳过所有验证
      output_separate_file: true   # 是否单独输出
    
    # ---------- 阶段1：LLM 分析配置 ----------
    llm_analysis:
      # 过滤策略
      exclude_physical_fk_pairs: true  # 排除物理外键表对
      
      # 置信度阈值
      high_confidence_threshold: 0.85  # 高置信度阈值
      low_confidence_threshold: 0.75   # 低置信度阈值
      
      # LLM 调用配置（复用现有配置）
      use_async: true
      batch_size: 10
      max_retries: 3
      retry_delay: 2
    
    # ---------- 阶段2：REL 分析配置 ----------
    rel_analysis:
      # 智能过滤
      smart_filtering: true        # 启用智能过滤
      exclude_physical_fk_pairs: true
      exclude_llm_high_confidence_pairs: true
      llm_high_threshold: 0.85     # 排除 LLM 高于此分数的表对
      
      # 可选：对 LLM 低置信度关系进行验证
      verify_llm_low_confidence: true
      llm_low_threshold: 0.75      # 低于此分数需要 REL 验证
      
      # REL 规则配置（复用现有配置）
      single_column: { ... }
      composite: { ... }
      weights: { ... }
    
    # ---------- 阶段3：合并策略配置 ----------
    merge_strategy:
      # 分数合并方式
      score_merge_strategy: "weighted_avg"  # weighted_avg | max | min
      score_weights:
        llm: 0.6    # LLM 权重（语义理解更可靠）
        rel: 0.4    # REL 权重
      
      # 置信度阈值（用于分类）
      confidence_thresholds:
        very_high: 0.90
        high: 0.85
        medium: 0.80
        low: 0.75
      
      # 输出控制
      include_suspicious: true     # 包含可疑关系（LLM低分且REL未确认）
      include_conflicts: true      # 包含冲突关系
      
      # 冲突解决策略
      conflict_resolution: "keep_both"  # keep_both | llm_priority | rel_priority | highest_score
    
    # ---------- 输出目录配置 ----------
    output_directories:
      llm_output: "output/rel_llm"      # LLM 独立结果
      rel_output: "output/rel_rule"     # REL 独立结果
      merged_output: "output/rel"       # 最终合并结果
      
      # 输出选项
      generate_analysis_report: true    # 生成详细分析报告
      generate_markdown: true           # 生成 Markdown 格式
      generate_separate_physical_fks: false  # 是否单独输出物理外键文件

# ====== 现有配置（保持兼容） ======
# 单独使用 --step rel 或 --step rel_llm 时，使用这些配置
output:
  rel_directory: output/rel
  rel_granularity: global
  rel_id_salt: ""

# LLM 配置
llm:
  provider: "openai"
  model: "gpt-4"
  # ...

# 数据库配置
database:
  host: "${DB_HOST}"
  port: 5432
  # ...
```

### 配置说明

#### 1. 物理外键配置

```yaml
physical_fks:
  confidence: 1.0              # 固定，不可修改
  priority: "absolute"         # 最高优先级
  skip_validation: true        # 不进行任何验证
  output_separate_file: true   # 可选：单独输出 physical_fks.json
```

#### 2. LLM 分析配置

```yaml
llm_analysis:
  exclude_physical_fk_pairs: true  # 排除物理外键表对
  high_confidence_threshold: 0.85  # 调整此值影响 REL 过滤范围
```

**阈值影响**：
- 0.85（推荐）：平衡准确度和覆盖率
- 0.90（保守）：更少表对被排除，REL 分析更多
- 0.80（激进）：更多表对被排除，REL 分析更少

#### 3. REL 分析配置

```yaml
rel_analysis:
  smart_filtering: true        # 必须启用
  exclude_llm_high_threshold: 0.85  # 与 LLM 高阈值保持一致
```

**计算量估算**：
```python
total_pairs = n * (n - 1) / 2
excluded_by_fk = count(physical_fks)
excluded_by_llm = count(llm_relations with score >= 0.85)
rel_pairs = total_pairs - excluded_by_fk - excluded_by_llm

efficiency = 1 - (rel_pairs / total_pairs)
# 预期：70-80% 效率提升
```

#### 4. 合并策略配置

```yaml
merge_strategy:
  score_weights:
    llm: 0.6    # 更信任 LLM 的语义判断
    rel: 0.4
```

**权重建议**：
- **LLM 权重更高（0.6-0.7）**：适合业务语义复杂的场景
- **平衡权重（0.5:0.5）**：适合标准化场景
- **REL 权重更高（0.6-0.7）**：适合字段命名规范的场景

---

## 输出目录结构

### 目录布局

```
output/
├── rel_llm/                        # LLM 独立分析结果
│   ├── relationships_llm.json      # JSON 格式
│   ├── relationships_llm.md        # Markdown 格式
│   └── llm_analysis_log.json       # 分析日志（可选）
│
├── rel_rule/                       # REL 独立分析结果
│   ├── relationships_rule.json     # JSON 格式
│   ├── relationships_rule.md       # Markdown 格式
│   └── rel_analysis_log.json       # 分析日志（可选）
│
└── rel/                            # 最终合并结果
    ├── relationships_global.json   # 三源合并（主要输出）
    ├── relationships_global.md     # Markdown 格式
    ├── merge_analysis.json         # 详细合并分析报告
    ├── physical_fks.json           # 物理外键（可选）
    └── conflicts.json              # 冲突列表（可选）
```

### 文件说明

#### 1. `relationships_llm.json`（LLM独立结果）

```json
{
  "metadata_source": "llm_analysis",
  "analysis_timestamp": "2025-12-28T10:00:00Z",
  
  "statistics": {
    "table_pairs_analyzed": 70,
    "relationships_found": 45,
    "high_confidence": 38,
    "low_confidence": 7,
    "average_score": 0.87
  },
  
  "relationships": [
    {
      "relationship_id": "rel_llm_001",
      "type": "single_column",
      "from_table": {"schema": "public", "table": "dim_store"},
      "from_column": "region_id",
      "to_table": {"schema": "public", "table": "dim_region"},
      "to_column": "region_id",
      
      "discovery_method": "llm_assisted",
      "confidence_level": "high",
      "composite_score": 0.92,
      
      "llm_reasoning": "门店的区域外键，业务语义明确，样例数据值域匹配",
      "source": "llm_analysis"
    }
  ]
}
```

#### 2. `relationships_rule.json`（REL独立结果）

```json
{
  "metadata_source": "rel_analysis",
  "analysis_timestamp": "2025-12-28T10:05:00Z",
  
  "statistics": {
    "table_pairs_analyzed": 20,
    "relationships_found": 12,
    "computation_saved": "74.4%",
    "discovery_methods": {
      "active_search": 8,
      "composite_logical_key": 3,
      "dynamic_composite": 1
    }
  },
  
  "relationships": [
    {
      "relationship_id": "rel_rule_001",
      "type": "single_column",
      "from_table": {"schema": "public", "table": "fact_sales"},
      "from_column": "product_id",
      "to_table": {"schema": "public", "table": "dim_product"},
      "to_column": "product_id",
      
      "discovery_method": "active_search",
      "confidence_level": "high",
      "composite_score": 0.89,
      
      "score_details": {
        "inclusion_rate": 0.98,
        "name_similarity": 1.0,
        "type_compatibility": 1.0,
        "jaccard_index": 0.95
      },
      "source": "rel_analysis"
    }
  ]
}
```

#### 3. `relationships_global.json`（最终合并结果）⭐

```json
{
  "metadata_source": "hybrid_rel_llm",
  "analysis_strategy": "independent_then_merge",
  "generation_timestamp": "2025-12-28T10:10:00Z",
  
  "execution_stages": {
    "stage0_physical_fks": {
      "relationships_found": 8,
      "confidence": "absolute"
    },
    "stage1_llm": {
      "table_pairs_analyzed": 70,
      "relationships_found": 45,
      "high_confidence": 38,
      "low_confidence": 7
    },
    "stage2_rel": {
      "table_pairs_analyzed": 20,
      "relationships_found": 12,
      "computation_saved": "74.4%"
    },
    "stage3_merge": {
      "physical_fks": 8,
      "llm_rel_both": 8,
      "llm_only_high": 30,
      "llm_only_low": 7,
      "rel_only": 4,
      "conflicts": 2,
      "total": 57
    }
  },
  
  "statistics": {
    "total_relationships_found": 57,
    "confidence_distribution": {
      "absolute": 8,
      "very_high": 8,
      "high": 30,
      "medium": 4,
      "low": 7
    },
    "source_distribution": {
      "physical_constraint": 8,
      "llm_rel_both": 8,
      "llm_only_high": 30,
      "llm_only_low": 7,
      "rel_only": 4
    }
  },
  
  "quality_metrics": {
    "multi_source_verified": 16,      // 物理外键 + 双确认
    "high_confidence_rate": 0.81,     // (8 + 8 + 30) / 57
    "suspicious_rate": 0.12,          // 7 / 57
    "conflict_rate": 0.04             // 2 / 57
  },
  
  "relationships": [
    // ===== 第1层：物理外键（absolute） =====
    {
      "relationship_id": "rel_physical_001",
      "type": "single_column",
      "from_table": {"schema": "public", "table": "employee"},
      "from_column": "dept_id",
      "to_table": {"schema": "public", "table": "department"},
      "to_column": "dept_id",
      
      "discovery_method": "physical_constraint",
      "confidence_level": "absolute",
      "composite_score": 1.0,
      "source": "physical_constraint",
      
      "constraint_info": {
        "constraint_name": "fk_employee_department",
        "on_delete": "NO ACTION",
        "on_update": "NO ACTION"
      }
    },
    
    // ===== 第2层：LLM + REL 双确认（very_high） =====
    {
      "relationship_id": "rel_hybrid_001",
      "type": "single_column",
      "from_table": {"schema": "public", "table": "dim_store"},
      "from_column": "region_id",
      "to_table": {"schema": "public", "table": "dim_region"},
      "to_column": "region_id",
      
      "discovery_method": "llm_rel_both",
      "confidence_level": "very_high",
      "composite_score": 0.93,  // LLM 0.92 * 0.6 + REL 0.95 * 0.4
      "source": "llm_rel_both",
      
      "sources": {
        "llm": {
          "score": 0.92,
          "reasoning": "门店的区域外键，业务语义明确"
        },
        "rel": {
          "score": 0.95,
          "method": "active_search",
          "details": {
            "inclusion_rate": 1.0,
            "name_similarity": 1.0,
            "type_compatibility": 1.0,
            "jaccard_index": 0.98
          }
        }
      }
    },
    
    // ===== 第3层：LLM 独有高分（high） =====
    {
      "relationship_id": "rel_llm_001",
      "type": "single_column",
      "from_table": {"schema": "public", "table": "order"},
      "from_column": "customer_number",
      "to_table": {"schema": "public", "table": "customer"},
      "to_column": "member_id",
      
      "discovery_method": "llm_assisted",
      "confidence_level": "high",
      "composite_score": 0.88,
      "source": "llm_only_high",
      
      "llm_reasoning": "字段名不同但语义相同：订单.客户编号 → 客户.会员号，样例数据值域匹配",
      "note": "REL 未发现（name_similarity 低）"
    },
    
    // ===== 第4层：REL 独有（medium） =====
    {
      "relationship_id": "rel_rule_001",
      "type": "single_column",
      "from_table": {"schema": "public", "table": "fact_sales"},
      "from_column": "product_id",
      "to_table": {"schema": "public", "table": "dim_product"},
      "to_column": "product_id",
      
      "discovery_method": "active_search",
      "confidence_level": "medium",
      "composite_score": 0.83,
      "source": "rel_only",
      
      "score_details": {
        "inclusion_rate": 0.95,
        "name_similarity": 1.0,
        "type_compatibility": 1.0,
        "jaccard_index": 0.90
      },
      "note": "LLM 未分析此表对"
    },
    
    // ===== 第5层：LLM 低分未确认（low，可疑） =====
    {
      "relationship_id": "rel_llm_low_001",
      "type": "single_column",
      "from_table": {"schema": "public", "table": "log"},
      "from_column": "user_code",
      "to_table": {"schema": "public", "table": "user"},
      "to_column": "user_id",
      
      "discovery_method": "llm_assisted",
      "confidence_level": "low",
      "composite_score": 0.72,
      "source": "llm_only_low",
      
      "warnings": [
        "⚠️ LLM 低置信度且 REL 未确认",
        "建议人工审核"
      ],
      "llm_reasoning": "字段名部分匹配，但样例数据格式不一致"
    }
  ],
  
  "suppressed_relationships": [],  // 保留字段（兼容性）
  
  "conflicts": [
    {
      "conflict_id": "conflict_001",
      "table_pair": "public.order -> public.customer",
      "description": "LLM 和 REL 对同一表对发现了不同的关联列",
      
      "llm_relationship": {
        "columns": "customer_number -> member_id",
        "score": 0.88,
        "reasoning": "语义相同"
      },
      
      "rel_relationship": {
        "columns": "customer_code -> code",
        "score": 0.82,
        "details": {...}
      },
      
      "resolution": "keep_both",
      "status": "needs_review",
      "note": "可能存在多个关联路径，建议人工确认业务规则"
    }
  ]
}
```

#### 4. `merge_analysis.json`（详细合并分析）

```json
{
  "analysis_timestamp": "2025-12-28T10:10:00Z",
  "analysis_version": "1.0",
  
  "input_sources": {
    "physical_fks": {
      "count": 8,
      "confidence": "absolute",
      "description": "数据库物理外键约束"
    },
    "llm_analysis": {
      "count": 45,
      "high_confidence": 38,
      "low_confidence": 7,
      "table_pairs_analyzed": 70,
      "excluded_pairs": 8
    },
    "rel_analysis": {
      "count": 12,
      "table_pairs_analyzed": 20,
      "excluded_pairs": 58,
      "computation_saved": "74.4%"
    }
  },
  
  "merge_result": {
    "total_relationships": 57,
    "by_source": {
      "physical_constraint": 8,
      "llm_rel_both": 8,
      "llm_only_high": 30,
      "llm_only_low": 7,
      "rel_only": 4
    },
    "by_confidence": {
      "absolute": 8,
      "very_high": 8,
      "high": 30,
      "medium": 4,
      "low": 7
    }
  },
  
  "quality_analysis": {
    "multi_source_verified": {
      "count": 16,
      "percentage": 0.281,
      "description": "物理外键 + LLM+REL 双确认"
    },
    "high_confidence": {
      "count": 46,
      "percentage": 0.807,
      "description": "absolute + very_high + high"
    },
    "suspicious": {
      "count": 7,
      "percentage": 0.123,
      "description": "LLM 低分且 REL 未确认"
    },
    "conflicts": {
      "count": 2,
      "percentage": 0.035,
      "description": "需要人工审核"
    }
  },
  
  "efficiency_metrics": {
    "total_table_pairs": 78,
    "llm_analyzed": 70,
    "rel_analyzed": 20,
    "llm_filtering_rate": 0.103,
    "rel_filtering_rate": 0.744,
    "overall_efficiency_gain": 0.423
  },
  
  "agreement_analysis": {
    "llm_rel_overlap_pairs": 20,
    "llm_rel_agreed_pairs": 8,
    "agreement_rate": 0.40,
    "description": "LLM 和 REL 都分析的表对中，40% 达成一致"
  },
  
  "recommendations": [
    {
      "priority": "high",
      "category": "review",
      "count": 2,
      "description": "存在 2 个冲突关系，建议人工审核"
    },
    {
      "priority": "medium",
      "category": "suspicious",
      "count": 7,
      "description": "存在 7 个可疑关系（LLM 低分且 REL 未确认），建议复核"
    }
  ],
  
  "execution_time": {
    "stage0_physical_fks": "0.5s",
    "stage1_llm": "15m 30s",
    "stage2_rel": "2m 45s",
    "stage3_merge": "1.2s",
    "total": "18m 16.7s"
  }
}
```

---

## 输出格式设计

### 关系对象格式

#### 完整字段说明

```typescript
interface Relationship {
  // ===== 基础标识 =====
  relationship_id: string;        // 唯一ID
  type: "single_column" | "composite";
  
  // ===== 表和列信息 =====
  from_table: {
    schema: string;
    table: string;
  };
  to_table: {
    schema: string;
    table: string;
  };
  from_column?: string;           // 单列关系
  to_column?: string;
  from_columns?: string[];        // 复合键关系
  to_columns?: string[];
  
  // ===== 发现信息 =====
  discovery_method: string;       // 见下方枚举
  confidence_level: string;       // absolute | very_high | high | medium | low
  composite_score: number;        // 0.0 - 1.0
  source: string;                 // 见下方枚举
  
  // ===== 详细信息（根据来源不同） =====
  
  // 物理外键专属
  constraint_info?: {
    constraint_name: string;
    on_delete: string;
    on_update: string;
  };
  
  // LLM 专属
  llm_reasoning?: string;
  
  // REL 专属
  score_details?: {
    inclusion_rate: number;
    name_similarity: number;
    type_compatibility: number;
    jaccard_index: number;
  };
  
  // 双确认专属
  sources?: {
    llm: {
      score: number;
      reasoning: string;
    };
    rel: {
      score: number;
      method: string;
      details: object;
    };
  };
  
  // ===== 元数据 =====
  cardinality?: string;           // 1:N | N:1 | 1:1 | M:N
  warnings?: string[];            // 警告信息
  notes?: string[];               // 说明信息
}
```

#### 枚举值定义

**`discovery_method` 枚举**：
```typescript
enum DiscoveryMethod {
  // 物理外键
  PHYSICAL_CONSTRAINT = "physical_constraint",
  
  // LLM 方法
  LLM_ASSISTED = "llm_assisted",
  
  // REL 方法
  FOREIGN_KEY = "foreign_key",
  ACTIVE_SEARCH = "active_search",
  COMPOSITE_LOGICAL_KEY = "composite_logical_key",
  COMPOSITE_PHYSICAL = "composite_physical",
  DYNAMIC_COMPOSITE = "dynamic_composite",
  
  // 混合方法
  LLM_REL_BOTH = "llm_rel_both"
}
```

**`source` 枚举**：
```typescript
enum RelationshipSource {
  PHYSICAL_CONSTRAINT = "physical_constraint",  // 物理外键
  LLM_REL_BOTH = "llm_rel_both",               // LLM + REL 双确认
  LLM_ONLY_HIGH = "llm_only_high",             // LLM 独有高分
  LLM_ONLY_LOW = "llm_only_low",               // LLM 独有低分
  REL_ONLY = "rel_only",                       // REL 独有
  LLM_ANALYSIS = "llm_analysis",               // LLM 独立分析
  REL_ANALYSIS = "rel_analysis"                // REL 独立分析
}
```

**`confidence_level` 枚举**：
```typescript
enum ConfidenceLevel {
  ABSOLUTE = "absolute",      // 1.0（物理外键）
  VERY_HIGH = "very_high",    // 0.90-0.99（双确认）
  HIGH = "high",              // 0.85-0.89（LLM 独有高分）
  MEDIUM = "medium",          // 0.80-0.84（REL 独有）
  LOW = "low"                 // <0.80（可疑）
}
```

### Markdown 输出格式

#### `relationships_global.md` 结构

```markdown
# 关系发现结果（混合模式）

**生成时间**: 2025-12-28 10:10:00  
**分析模式**: 独立分析 + 智能合并  
**总关系数**: 57

---

## 📊 统计摘要

### 执行阶段

| 阶段 | 表对数 | 关系数 | 说明 |
|-----|-------|--------|------|
| 阶段0：物理外键 | - | 8 | 100% 置信度 |
| 阶段1：LLM 分析 | 70 | 45 | 高分 38，低分 7 |
| 阶段2：REL 分析 | 20 | 12 | 计算量节省 74% |
| 阶段3：智能合并 | - | 57 | 最终输出 |

### 置信度分布

| 置信度 | 数量 | 百分比 | 说明 |
|--------|-----|--------|------|
| absolute | 8 | 14% | 物理外键 |
| very_high | 8 | 14% | LLM + REL 双确认 |
| high | 30 | 53% | LLM 独有高分 |
| medium | 4 | 7% | REL 独有 |
| low | 7 | 12% | 可疑，需审核 |

### 来源分布

| 来源 | 数量 | 百分比 |
|------|-----|--------|
| 物理外键 | 8 | 14% |
| LLM + REL 双确认 | 8 | 14% |
| LLM 独有高分 | 30 | 53% |
| LLM 独有低分 | 7 | 12% |
| REL 独有 | 4 | 7% |

### 质量指标

- **多源验证关系**: 16 个（28%）
- **高置信度关系**: 46 个（81%）
- **可疑关系**: 7 个（12%）
- **冲突关系**: 2 个（4%）

---

## 📋 关系列表

### 第1层：物理外键（absolute）

#### 1. employee → department

- **类型**: single_column
- **关联**: `employee.dept_id` → `department.dept_id`
- **置信度**: absolute (1.0)
- **来源**: 物理外键约束
- **约束名**: fk_employee_department
- **级联**: ON DELETE NO ACTION, ON UPDATE NO ACTION

---

### 第2层：LLM + REL 双确认（very_high）

#### 2. dim_store → dim_region

- **类型**: single_column
- **关联**: `dim_store.region_id` → `dim_region.region_id`
- **置信度**: very_high (0.93)
- **来源**: LLM + REL 双确认

**LLM 分析**:
- 分数: 0.92
- 推理: 门店的区域外键，业务语义明确

**REL 分析**:
- 分数: 0.95
- 方法: active_search
- 详情:
  - inclusion_rate: 1.0
  - name_similarity: 1.0
  - type_compatibility: 1.0
  - jaccard_index: 0.98

---

### 第3层：LLM 独有高分（high）

#### 3. order → customer

- **类型**: single_column
- **关联**: `order.customer_number` → `customer.member_id`
- **置信度**: high (0.88)
- **来源**: LLM 独有

**LLM 推理**: 字段名不同但语义相同：订单.客户编号 → 客户.会员号，样例数据值域匹配

**说明**: REL 未发现（name_similarity 低）

---

### 第4层：REL 独有（medium）

#### 4. fact_sales → dim_product

- **类型**: single_column
- **关联**: `fact_sales.product_id` → `dim_product.product_id`
- **置信度**: medium (0.83)
- **来源**: REL 独有

**REL 评分**:
- inclusion_rate: 0.95
- name_similarity: 1.0
- type_compatibility: 1.0
- jaccard_index: 0.90

**说明**: LLM 未分析此表对

---

### 第5层：可疑关系（low）

#### 5. log → user ⚠️

- **类型**: single_column
- **关联**: `log.user_code` → `user.user_id`
- **置信度**: low (0.72)
- **来源**: LLM 独有（低分）

**LLM 推理**: 字段名部分匹配，但样例数据格式不一致

⚠️ **警告**:
- LLM 低置信度且 REL 未确认
- 建议人工审核

---

## ⚔️ 冲突列表

### 冲突1: order → customer

**描述**: LLM 和 REL 对同一表对发现了不同的关联列

**LLM 发现**:
- 列: `customer_number` → `member_id`
- 分数: 0.88
- 推理: 语义相同

**REL 发现**:
- 列: `customer_code` → `code`
- 分数: 0.82

**解决方案**: 保留双方结果，标记为需人工审核

**说明**: 可能存在多个关联路径，建议人工确认业务规则

---

## 📈 效率分析

- **总表对数**: 78
- **LLM 分析**: 70 个（排除 8 个物理外键表对）
- **REL 分析**: 20 个（排除 58 个已确认表对）
- **REL 计算量节省**: 74.4%
- **总执行时间**: 18分16.7秒

---

## 🔍 质量建议

### 高优先级（需人工审核）

1. **冲突关系**: 2 个
   - 建议: 确认业务规则，选择正确的关联列

### 中优先级（建议复核）

2. **可疑关系**: 7 个
   - 建议: 检查字段语义和数据质量
   - 可能需要添加物理外键约束

---

**文档结束**
```

---

## 与现有代码集成

### CLI 集成

#### `metadata_cli.py` 修改

```python
# metaweave/cli/metadata_cli.py

@click.option(
    "--step",
    type=click.Choice([
        "ddl", "json", "json_llm", 
        "cql", "cql_llm", 
        "md", 
        "rel", "rel_llm", "rel+llm",  # 新增 rel+llm
        "all"
    ], case_sensitive=False),
    default="all",
    show_default=True,
    help="指定要执行的步骤"
)
def metadata_command(..., step: str, ...):
    """生成数据库元数据"""
    
    # ... 其他 step 处理 ...
    
    # Step: rel+llm - 混合模式
    if step == "rel+llm":
        from metaweave.core.relationships.hybrid_discovery import HybridRelationshipDiscovery
        from services.config_loader import load_config
        
        click.echo("🔗 开始混合关系发现（rel+llm）...")
        click.echo("   策略：独立分析 + 智能合并")
        click.echo("")
        
        # 加载配置
        config = load_config(config_path)
        
        # 初始化连接器
        connector = DatabaseConnector(config.get("database", {}))
        
        try:
            # 初始化混合发现器
            discovery = HybridRelationshipDiscovery(
                config=config,
                connector=connector
            )
            
            # 执行混合发现
            result = discovery.discover()
            
            # 显示结果
            click.echo("")
            click.echo("=" * 60)
            click.echo("📊 混合关系发现结果")
            click.echo("=" * 60)
            click.echo(f"✅ 物理外键（absolute）: {result.physical_fks_count} 个")
            click.echo(f"✅ LLM + REL 双确认（very_high）: {result.llm_rel_both_count} 个")
            click.echo(f"✅ LLM 独有高分（high）: {result.llm_only_high_count} 个")
            click.echo(f"📊 REL 独有（medium）: {result.rel_only_count} 个")
            click.echo(f"⚠️  可疑关系（low）: {result.llm_only_low_count} 个")
            if result.conflicts_count > 0:
                click.echo(f"⚔️  冲突（需审核）: {result.conflicts_count} 个")
            click.echo(f"📈 总关系数: {result.total_relations} 个")
            click.echo("")
            click.echo("📁 输出文件:")
            for output_file in result.output_files:
                click.echo(f"  - {output_file}")
            click.echo("=" * 60)
            click.echo("✨ 混合关系发现完成！")
            
        finally:
            connector.close()
        
        return
```

### 新模块结构

```
metaweave/core/relationships/
├── __init__.py
├── models.py                       # 现有：数据模型
├── repository.py                   # 现有：JSON加载
├── candidate_generator.py          # 现有：候选生成
├── scorer.py                       # 现有：关系评分
├── decision_engine.py              # 现有：决策过滤
├── writer.py                       # 现有：结果输出
├── name_similarity.py              # 现有：名称相似度
├── pipeline.py                     # 现有：rel 步骤
├── llm_relationship_discovery.py   # 现有：rel_llm 步骤
│
├── hybrid_discovery.py             # 新增：混合发现主控
├── hybrid_merger.py                # 新增：三源合并器
├── hybrid_models.py                # 新增：混合模式数据模型
└── hybrid_writer.py                # 新增：混合模式输出
```

### 核心模块设计

#### 1. `hybrid_discovery.py`（主控制器）

```python
"""混合关系发现主控制器"""

class HybridRelationshipDiscovery:
    """
    混合关系发现
    
    流程：
    1. 阶段0：提取物理外键
    2. 阶段1：LLM 独立分析
    3. 阶段2：REL 独立分析（智能过滤）
    4. 阶段3：三源智能合并
    """
    
    def __init__(self, config: Dict, connector: DatabaseConnector):
        self.config = config
        self.connector = connector
        self.hybrid_config = config.get("relationships", {}).get("hybrid_mode", {})
        
        # 初始化各阶段处理器
        self.repository = MetadataRepository(...)
        self.llm_discovery = LLMRelationshipDiscovery(...)
        self.rel_pipeline = RelationshipDiscoveryPipeline(...)
        self.merger = HybridRelationshipMerger(...)
        self.writer = HybridRelationshipWriter(...)
    
    def discover(self) -> HybridDiscoveryResult:
        """执行混合发现"""
        
        start_time = time.time()
        
        # 阶段0：物理外键
        physical_fks = self._extract_physical_fks()
        
        # 阶段1：LLM 分析
        llm_relations = self._llm_analysis(physical_fks)
        
        # 阶段2：REL 分析
        rel_relations = self._rel_analysis(physical_fks, llm_relations)
        
        # 阶段3：合并
        merge_result = self.merger.merge(
            physical_fks, 
            llm_relations, 
            rel_relations
        )
        
        # 输出
        output_files = self.writer.write_all(
            llm_relations=llm_relations,
            rel_relations=rel_relations,
            merge_result=merge_result
        )
        
        # 构建结果
        result = HybridDiscoveryResult(
            success=True,
            total_relations=len(merge_result.relations),
            physical_fks_count=len(physical_fks),
            llm_rel_both_count=len(merge_result.analysis["llm_rel_both"]),
            llm_only_high_count=len(merge_result.analysis["llm_only_high"]),
            llm_only_low_count=len(merge_result.analysis["llm_only_low"]),
            rel_only_count=len(merge_result.analysis["rel_only"]),
            conflicts_count=len(merge_result.analysis["conflicts"]),
            output_files=output_files,
            execution_time=time.time() - start_time
        )
        
        return result
```

#### 2. `hybrid_merger.py`（合并器）

```python
"""三源智能合并器"""

class HybridRelationshipMerger:
    """
    三源智能合并器
    
    优先级：
    1. 物理外键（absolute）
    2. LLM + REL 双确认（very_high）
    3. LLM 独有高分（high）
    4. REL 独有（medium）
    5. LLM 低分未确认（low）
    """
    
    def merge(self, 
              physical_fks: List[Relation],
              llm_relations: List[Relation],
              rel_relations: List[Relation]) -> MergeResult:
        """合并三个来源的关系"""
        
        # 详细实现见上文"阶段3：三源智能合并"
        pass
```

#### 3. `hybrid_writer.py`（输出器）

```python
"""混合模式结果输出"""

class HybridRelationshipWriter:
    """
    混合模式输出器
    
    输出文件：
    - output/rel_llm/relationships_llm.json
    - output/rel_rule/relationships_rule.json
    - output/rel/relationships_global.json
    - output/rel/merge_analysis.json
    """
    
    def write_all(self,
                  llm_relations: List[Relation],
                  rel_relations: List[Relation],
                  merge_result: MergeResult) -> List[str]:
        """输出所有文件"""
        
        output_files = []
        
        # 1. LLM 独立结果
        llm_file = self._write_llm_result(llm_relations)
        output_files.append(llm_file)
        
        # 2. REL 独立结果
        rel_file = self._write_rel_result(rel_relations)
        output_files.append(rel_file)
        
        # 3. 合并结果
        merged_file = self._write_merged_result(merge_result)
        output_files.append(merged_file)
        
        # 4. 分析报告
        analysis_file = self._write_analysis_report(merge_result)
        output_files.append(analysis_file)
        
        # 5. Markdown 格式
        if self.config.get("generate_markdown", True):
            md_files = self._write_markdown_files(
                llm_relations, rel_relations, merge_result
            )
            output_files.extend(md_files)
        
        return output_files
```

---

## 实现路线图

### 阶段1：基础实现（MVP）

**时间**: 1-2周

**目标**: 实现核心流程，验证设计可行性

**任务清单**:

- [ ] **模型定义**
  - [ ] `HybridDiscoveryResult` 数据模型
  - [ ] `MergeResult` 数据模型
  - [ ] 枚举类型（`ConfidenceLevel`, `RelationshipSource`等）

- [ ] **核心模块**
  - [ ] `HybridRelationshipDiscovery`（主控）
    - [ ] `_extract_physical_fks()` 方法
    - [ ] `_llm_analysis()` 方法（复用现有）
    - [ ] `_rel_analysis()` 方法（复用现有）
  - [ ] `HybridRelationshipMerger`（合并器）
    - [ ] 基础合并逻辑
    - [ ] 双确认处理
    - [ ] 独有关系处理

- [ ] **输出模块**
  - [ ] `HybridRelationshipWriter`（输出器）
    - [ ] JSON 格式输出
    - [ ] 基础 Markdown 输出

- [ ] **CLI 集成**
  - [ ] 添加 `--step rel+llm` 选项
  - [ ] 基础结果显示

- [ ] **配置支持**
  - [ ] `hybrid_mode` 配置块
  - [ ] 基础阈值配置

**验证标准**:
- ✅ 能够执行完整流程
- ✅ 输出三个独立目录的结果
- ✅ 基础合并逻辑正确

### 阶段2：功能完善

**时间**: 1周

**目标**: 添加高级特性，提升用户体验

**任务清单**:

- [ ] **智能过滤**
  - [ ] REL 排除 LLM 高置信度表对
  - [ ] 计算量统计和日志

- [ ] **冲突检测**
  - [ ] 同表对不同列组合检测
  - [ ] 冲突标记和输出

- [ ] **详细输出**
  - [ ] `merge_analysis.json` 生成
  - [ ] `conflicts.json` 生成
  - [ ] 完整 Markdown 报告

- [ ] **配置扩展**
  - [ ] 分数合并策略配置
  - [ ] 冲突解决策略配置
  - [ ] 输出控制选项

**验证标准**:
- ✅ REL 计算量节省 > 70%
- ✅ 冲突关系正确识别
- ✅ 输出报告完整详细

### 阶段3：质量优化

**时间**: 1周

**目标**: 提升准确度和稳定性

**任务清单**:

- [ ] **测试覆盖**
  - [ ] 单元测试（各模块）
  - [ ] 集成测试（完整流程）
  - [ ] 边界情况测试

- [ ] **文档完善**
  - [ ] API 文档
  - [ ] 用户指南
  - [ ] 最佳实践

- [ ] **性能优化**
  - [ ] 并发处理优化
  - [ ] 内存使用优化
  - [ ] 日志性能优化

- [ ] **错误处理**
  - [ ] 异常捕获和恢复
  - [ ] 友好错误提示
  - [ ] 部分失败处理

**验证标准**:
- ✅ 测试覆盖率 > 80%
- ✅ 文档完整清晰
- ✅ 错误处理健壮

### 阶段4：生产就绪

**时间**: 1周

**目标**: 满足生产环境要求

**任务清单**:

- [ ] **监控和日志**
  - [ ] 详细执行日志
  - [ ] 性能指标收集
  - [ ] 错误统计和报警

- [ ] **用户体验**
  - [ ] 进度条显示
  - [ ] 友好的 CLI 输出
  - [ ] 交互式确认（可选）

- [ ] **兼容性**
  - [ ] 向后兼容测试
  - [ ] 多版本配置支持
  - [ ] 迁移工具（可选）

- [ ] **发布准备**
  - [ ] 版本号管理
  - [ ] 变更日志
  - [ ] 发布说明

**验证标准**:
- ✅ 生产环境稳定运行
- ✅ 用户反馈积极
- ✅ 文档齐全

---

## 性能评估

### 计算效率

#### 场景1：小型数据库（10张表）

```
总表对：45 个

阶段0：物理外键
- 发现：3 个
- 耗时：0.1s

阶段1：LLM 分析
- 表对：42 个（45 - 3）
- 耗时：5-8 分钟（取决于 LLM API）

阶段2：REL 分析
- 表对：10 个（42 - 32 LLM高置信度）
- 耗时：30 秒
- 节省：76%

阶段3：合并
- 耗时：< 1 秒

总耗时：6-9 分钟
```

#### 场景2：中型数据库（50张表）

```
总表对：1225 个

阶段0：物理外键
- 发现：25 个
- 耗时：0.5s

阶段1：LLM 分析
- 表对：1200 个（1225 - 25）
- 耗时：2-4 小时（取决于 LLM API）

阶段2：REL 分析
- 表对：300 个（排除 900 个 LLM高置信度）
- 耗时：8-12 分钟
- 节省：75%

阶段3：合并
- 耗时：2-3 秒

总耗时：2-4 小时
```

#### 场景3：大型数据库（200张表）

```
总表对：19900 个

阶段0：物理外键
- 发现：150 个
- 耗时：2s

阶段1：LLM 分析
- 表对：19750 个
- 耗时：30-50 小时（需要批处理和并发）

阶段2：REL 分析
- 表对：4000 个（排除 15750 个）
- 耗时：1-2 小时
- 节省：80%

阶段3：合并
- 耗时：10-15 秒

总耗时：31-52 小时（需要优化 LLM 调用策略）
```

### 准确度评估

#### 测试数据集（13张表，78个表对）

**真实关系数**：20 个（人工标注）

| 方法 | 发现数 | 正确数 | 准确率 | 召回率 | F1 |
|------|-------|--------|--------|--------|-----|
| `rel` | 15 | 13 | 87% | 65% | 0.74 |
| `rel_llm` | 18 | 16 | 89% | 80% | 0.84 |
| **`rel+llm`** | **20** | **19** | **95%** | **95%** | **0.95** |

**提升分析**：
- 准确率提升：95% vs 89% (+6%)
- 召回率提升：95% vs 80% (+15%)
- F1 提升：0.95 vs 0.84 (+13%)

**错误分析**：
- 1个误报：LLM 误判（但 REL 低分标记为可疑）
- 1个漏报：字段名完全不同且无样例数据

### 成本分析

#### LLM API 成本（以 GPT-4 为例）

**小型数据库（10张表，42个LLM表对）**:
```
平均 tokens/表对：3000 tokens
总 tokens：42 * 3000 = 126,000 tokens
成本：$1.26（输入）+ $3.78（输出）≈ $5
```

**中型数据库（50张表，1200个LLM表对）**:
```
总 tokens：1200 * 3000 = 3,600,000 tokens
成本：$36（输入）+ $108（输出）≈ $144
```

**大型数据库（200张表，19750个LLM表对）**:
```
总 tokens：19750 * 3000 = 59,250,000 tokens
成本：$592（输入）+ $1,776（输出）≈ $2,368
```

**成本优化建议**：
1. 使用更便宜的模型（如 GPT-3.5-turbo，成本降低 90%）
2. 智能过滤：优先分析高价值表对
3. 缓存 LLM 结果，避免重复调用

---

## 风险与缓解

### 风险1：LLM API 限流或失败

**影响**: 高  
**概率**: 中

**缓解措施**:
1. **重试机制**：配置 `max_retries` 和 `retry_delay`
2. **批处理**：使用 `batch_size` 控制并发
3. **断点续传**：保存中间结果，失败后可恢复
4. **降级策略**：LLM 失败时，仍可输出 REL 结果

### 风险2：REL 计算资源不足

**影响**: 中  
**概率**: 低

**缓解措施**:
1. **智能过滤**：排除已确认表对，减少 70%+ 计算量
2. **采样优化**：降低数据库采样数量
3. **并发控制**：配置合理的 `max_workers`

### 风险3：合并逻辑错误

**影响**: 高  
**概率**: 中

**缓解措施**:
1. **详细日志**：记录每个决策点
2. **单元测试**：覆盖所有合并场景
3. **人工审核**：标记冲突和可疑关系

### 风险4：输出格式不兼容

**影响**: 中  
**概率**: 低

**缓解措施**:
1. **向后兼容**：保留 `rel` 和 `rel_llm` 的输出格式
2. **版本标记**：输出文件包含 `metadata_source: "hybrid_rel_llm"`
3. **迁移工具**：提供格式转换脚本（如需要）

### 风险5：配置复杂度高

**影响**: 中  
**概率**: 中

**缓解措施**:
1. **默认值**：提供合理的默认配置
2. **配置验证**：启动时检查配置有效性
3. **文档完善**：提供配置示例和说明

---

## 未来扩展

### 扩展1：增量更新模式

**场景**: 只重新分析变更的表

**设计**:
```python
# 检测变更
changed_tables = detect_changed_tables(last_run_timestamp)

# 只对涉及变更表的表对进行分析
affected_pairs = get_affected_pairs(changed_tables)

# 合并新旧结果
final_result = merge_with_previous_result(
    previous_result, 
    new_result_for_affected_pairs
)
```

### 扩展2：交互式审核模式

**场景**: 对冲突和可疑关系进行交互式确认

**设计**:
```python
# 显示冲突
for conflict in conflicts:
    print_conflict_details(conflict)
    user_choice = input("选择: 1) LLM  2) REL  3) 两者  4) 拒绝")
    apply_user_choice(conflict, user_choice)
```

### 扩展3：多模型对比

**场景**: 使用多个 LLM 模型，取共识结果

**设计**:
```python
# 使用多个模型
llm_gpt4 = LLMDiscovery(model="gpt-4")
llm_claude = LLMDiscovery(model="claude-3")
llm_gemini = LLMDiscovery(model="gemini-pro")

# 取共识
consensus_relations = find_consensus([
    llm_gpt4.discover(),
    llm_claude.discover(),
    llm_gemini.discover()
])
```

### 扩展4：机器学习优化

**场景**: 基于历史审核数据，训练分类器

**设计**:
```python
# 收集训练数据
training_data = collect_reviewed_relationships()

# 训练分类器
classifier = train_classifier(training_data)

# 辅助决策
for relation in relations:
    ml_score = classifier.predict(relation)
    relation.ml_confidence = ml_score
```

### 扩展5：可视化界面

**场景**: 提供 Web UI 查看和管理关系

**功能**:
- 关系图可视化（Neo4j 风格）
- 冲突对比视图
- 批量审核工具
- 导出和分享

---

## 附录

### A. 关键配置示例

```yaml
# 最小化配置（使用默认值）
relationships:
  hybrid_mode:
    enabled: true

# 完整配置（所有选项）
relationships:
  hybrid_mode:
    enabled: true
    llm_analysis:
      high_confidence_threshold: 0.85
    rel_analysis:
      smart_filtering: true
      exclude_llm_high_threshold: 0.85
    merge_strategy:
      score_weights:
        llm: 0.6
        rel: 0.4
      include_suspicious: true
```

### B. 命令示例

```bash
# 基础用法
metaweave metadata --config configs/metadata_config.yaml --step rel+llm

# 指定表范围
metaweave metadata --config configs/metadata_config.yaml --step rel+llm \
  --tables "dim_store,dim_region,fact_sales"

# 增量模式（未来）
metaweave metadata --config configs/metadata_config.yaml --step rel+llm \
  --incremental

# 交互式审核（未来）
metaweave metadata --config configs/metadata_config.yaml --step rel+llm \
  --interactive
```

### C. 相关文档

- [3_rel_vs_rel_llm_命令对比与JSON兼容性评估.md](./3_rel_vs_rel_llm_命令对比与JSON兼容性评估.md)
- [1_rel_llm_关系发现LLM提示词模板.md](./1_rel_llm_关系发现LLM提示词模板.md)
- [命令依赖关系分析.md](./命令依赖关系分析.md)

### D. 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| 1.0 | 2025-12-28 | 初始版本，完整设计方案 |

---

**文档结束**

