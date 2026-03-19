"""候选关系生成器

负责生成候选关系（复合键优先，单列其次），排除已存在的外键。
"""

from typing import Dict, List, Set, Any, Optional, Tuple
from difflib import SequenceMatcher
from itertools import permutations, combinations

from metaweave.core.relationships.name_similarity import NameSimilarityService
from metaweave.core.relationships.type_compatibility import get_type_compatibility_score
from metaweave.utils.logger import get_metaweave_logger

logger = get_metaweave_logger("relationships.candidate_generator")


class CandidateGenerator:
    """候选关系生成器

    生成顺序：
    1. 复合键候选（物理约束、逻辑键、动态同名）
    2. 单列候选（主动搜索、逻辑键匹配）
    """

    def __init__(
            self,
            config: dict,
            fk_signature_set: Set[str],
            name_similarity_service: Optional[NameSimilarityService] = None,
    ):
        """初始化候选生成器

        Args:
            config: relationships配置（要求完整配置，不设默认值以暴露配置问题）
            fk_signature_set: 外键签名集合（用于去重）
        """
        self.config = config
        self.fk_signature_set = fk_signature_set
        self.name_similarity_service = name_similarity_service

        # 单列配置（single_column 节点）
        single_config = config["single_column"]
        self.important_constraints = set(single_config["important_constraints"])
        self.exclude_semantic_roles = set(single_config["exclude_semantic_roles"])
        self.single_logical_key_min_confidence = single_config["logical_key_min_confidence"]
        self.single_min_type_compatibility = single_config["min_type_compatibility"]
        self.single_name_similarity_important_target = single_config["name_similarity_important_target"]
        self.name_similarity_normal_target = single_config["name_similarity_normal_target"]

        # 复合键配置（composite 节点）
        composite_config = config["composite"]
        self.max_columns = composite_config["max_columns"]
        self.composite_min_type_compatibility = composite_config["min_type_compatibility"]
        self.composite_logical_key_min_confidence = composite_config["logical_key_min_confidence"]
        self.composite_name_similarity_important_target = composite_config["name_similarity_important_target"]

        # 复合键排除的语义角色（从配置读取，默认只排除 metric）
        # ⚠️ 关键：这个配置必须与 LogicalKeyDetector 中的 composite_exclude_roles 来自相同的 YAML 配置
        # 默认值保守策略：只排除明确不适合的 metric，description 等其他角色由用户根据实际情况选择
        self.composite_exclude_semantic_roles = set(
            composite_config.get("exclude_semantic_roles", ["metric"])
        )

        logger.info(f"候选生成器已初始化:")
        logger.info(f"  单列配置: important_target_sim={self.single_name_similarity_important_target}, "
                    f"normal_target_sim={self.name_similarity_normal_target}, "
                    f"type_compat>={self.single_min_type_compatibility}")
        logger.info(f"  复合键配置: max_columns={self.max_columns}, "
                    f"important_target_sim={self.composite_name_similarity_important_target}, "
                    f"type_compat>={self.composite_min_type_compatibility}")
        logger.info(f"  复合键排除角色（从配置）: {self.composite_exclude_semantic_roles}")

    def generate_candidates(self, tables: Dict[str, dict]) -> List[Dict[str, Any]]:
        """生成所有候选关系

        Args:
            tables: 表元数据字典 {full_name: json_data}

        Returns:
            候选列表，每个候选包含：
            - source/target: 表元数据
            - source_columns/target_columns: 列名列表
            - candidate_type: 候选类型
        """
        candidates = []

        # 1. 复合键候选（优先）
        composite_candidates = self._generate_composite_candidates(tables)
        candidates.extend(composite_candidates)
        logger.info(f"生成复合键候选: {len(composite_candidates)} 个")

        # 2. 单列候选
        single_candidates = self._generate_single_column_candidates(tables)
        candidates.extend(single_candidates)
        logger.info(f"生成单列候选: {len(single_candidates)} 个")

        logger.info(f"候选生成完成: 共 {len(candidates)} 个")
        return candidates

    def _generate_composite_candidates(self, tables: Dict[str, dict]) -> List[Dict[str, Any]]:
        """生成复合键候选

        来源：
        1. physical_constraints（PK/UK，不含索引）
        2. unique_column_sets（逻辑主键候选，confidence >= 配置阈值）
        3. dynamic_same_name（精确同名 + 类型兼容）
        
        注意：索引已完全排除在候选生成逻辑之外
        """
        candidates = []

        for source_name, source_table in tables.items():
            source_info = source_table.get("table_info", {})
            source_schema = source_info.get("schema_name")
            source_table_name = source_info.get("table_name")

            # 收集源表的复合键组合（仅包含 PK/UK/逻辑键，不含索引）
            source_combinations = self._collect_source_combinations(source_table)

            # 对每个组合，在目标表中查找匹配
            for combo in source_combinations:
                source_columns = combo["columns"]
                combo_type = combo["type"]

                # 遍历所有目标表（排除自己）
                for target_name, target_table in tables.items():
                    if target_name == source_name:
                        continue

                    target_info = target_table.get("table_info", {})
                    target_schema = target_info.get("schema_name")
                    target_table_name = target_info.get("table_name")

                    # 检查FK去重
                    fk_sig = self._make_signature(
                        source_schema, source_table_name, source_columns,
                        target_schema, target_table_name, source_columns  # 临时用source_columns
                    )

                    # 根据target_sources查找目标列
                    target_columns = self._find_target_columns(
                        source_columns, source_table, target_table, combo_type
                    )

                    if not target_columns:
                        continue

                    # 更新FK签名（使用实际的target_columns）
                    fk_sig = self._make_signature(
                        source_schema, source_table_name, source_columns,
                        target_schema, target_table_name, target_columns
                    )

                    if fk_sig in self.fk_signature_set:
                        continue

                    # 创建候选
                    candidate = {
                        "source": source_table,
                        "target": target_table,
                        "source_columns": source_columns,
                        "target_columns": target_columns,
                        "candidate_type": f"composite_{combo_type}"
                    }
                    candidates.append(candidate)

        return candidates

    def _collect_source_combinations(
            self,
            table: dict
    ) -> List[Dict[str, Any]]:
        """收集表的复合键组合（仅物理约束和逻辑键，不含索引）

        Args:
            table: 表元数据

        Returns:
            [{"columns": [...], "type": "physical|logical"}]
            
        说明：
            - physical: PK/UK (不含索引)
            - logical: unique_column_sets (置信度 >= 配置阈值)
        """
        combinations = []
        table_profile = table.get("table_profile", {})
        physical = table_profile.get("physical_constraints", {})

        # 1. 主键（总是收集）
        pk = physical.get("primary_key")
        if pk and pk.get("columns"):
            pk_cols = pk["columns"]
            if 2 <= len(pk_cols) <= self.max_columns:
                combinations.append({"columns": pk_cols, "type": "physical"})

        # 2. 唯一约束（总是收集）
        for uk in physical.get("unique_constraints", []):
            uk_cols = uk.get("columns", [])
            if 2 <= len(uk_cols) <= self.max_columns:
                combinations.append({"columns": uk_cols, "type": "physical"})

        # 3. 逻辑主键（总是收集）
        unique_column_sets = table_profile.get("unique_column_sets", [])
        table_name = table.get("table_info", {}).get("table_name", "unknown")
        logger.debug(f"[_collect_source_combinations] 表 {table_name} 的逻辑主键候选数: {len(unique_column_sets)}")
        
        for lk in unique_column_sets:
            lk_cols = lk.get("columns", [])
            lk_conf = lk.get("confidence_score", 0)
            logger.debug(f"[_collect_source_combinations] 检查逻辑主键: {table_name}{lk_cols}, conf={lk_conf}, len={len(lk_cols)}")
            
            if 2 <= len(lk_cols) <= self.max_columns and lk_conf >= self.composite_logical_key_min_confidence:
                combinations.append({"columns": lk_cols, "type": "logical"})
                logger.debug(f"[_collect_source_combinations] ✓ 收集逻辑主键: {table_name}{lk_cols}")
            else:
                logger.debug(f"[_collect_source_combinations] ✗ 跳过逻辑主键: {table_name}{lk_cols} (len={len(lk_cols)}, conf={lk_conf}, max={self.max_columns}, min_conf={self.composite_logical_key_min_confidence})")

        return combinations

    def _collect_target_combinations_for_privilege_mode(self, table: dict) -> List[Dict[str, Any]]:
        """收集目标表 Stage 1（特权模式）候选组合：PK/UK/UCCs + 多列索引

        说明：
            - 该函数只用于 Stage 1 的目标侧候选池（外键表侧强信号）
            - 源表组合收集仍保持“仅 PK/UK/UCCs，不含索引”
            - 索引不要求 is_unique
        """
        combos = list(self._collect_source_combinations(table))
        table_profile = table.get("table_profile", {})

        def _key(cols: List[str]) -> tuple[int, frozenset]:
            return len(cols), frozenset(cols)

        seen = {_key(c.get("columns", [])) for c in combos if c.get("columns")}

        for idx in table_profile.get("indexes", []) or []:
            cols = idx.get("columns", []) or []
            if 2 <= len(cols) <= self.max_columns:
                k = _key(cols)
                if k in seen:
                    continue
                combos.append({"columns": cols, "type": "index"})
                seen.add(k)

        return combos

    def _find_target_columns(
            self,
            source_columns: List[str],
            source_table: dict,
            target_table: dict,
            combo_type: str
    ) -> Optional[List[str]]:
        """在目标表中查找匹配的列组合（两阶段策略）

        Stage 1: 特权模式（Privilege Mode）
            - 当源表是 PK/UK/逻辑键时，检查目标表是否有相同性质的约束
            - 使用穷举排列算法 + 较低的名称相似度阈值
            - 如果匹配成功，立即返回（短路）

        Stage 2: 动态同名匹配（Dynamic Same-Name）
            - 总是执行，不依赖 Stage 1 的结果
            - 大小写不敏感的列名匹配 + 类型兼容性检查
            - 如果匹配成功，返回

        Args:
            source_columns: 源列列表
            source_table: 源表元数据
            target_table: 目标表元数据
            combo_type: 组合类型（physical|logical）

        Returns:
            目标列列表（顺序与源列对应），未找到返回None
        """
        source_profiles = source_table.get("column_profiles", {})
        target_profiles = target_table.get("column_profiles", {})

        # ============================================================
        # Stage 1: 特权模式（Privilege Mode）
        # ============================================================
        source_table_name = source_table.get("table_info", {}).get("table_name", "unknown")
        target_table_name = target_table.get("table_info", {}).get("table_name", "unknown")
        
        if combo_type in ["physical", "logical"]:
            # 收集目标表的候选组合（PK/UK/逻辑键 + 索引）
            # 注意：索引只在目标侧 Stage 1 使用（作为外键表的强信号），不影响源表组合收集逻辑
            target_combinations = self._collect_target_combinations_for_privilege_mode(target_table)

            logger.debug(
                "[find_target_columns] %s%s → %s: Stage 1 开始（combo_type=%s, 目标约束数=%d）",
                source_table_name, source_columns, target_table_name, combo_type, len(target_combinations)
            )

            # 遍历目标表的所有约束组合
            for target_combo in target_combinations:
                target_cols = target_combo["columns"]
                target_combo_type = target_combo["type"]

                logger.debug(
                    "[find_target_columns] Stage 1: 尝试匹配目标约束 %s%s (type=%s)",
                    target_table_name, target_cols, target_combo_type
                )

                # 目标列数必须 >= 源列数（支持乱序子集匹配，例如源(A,B) 匹配 目标(A,B,C) 的任意2列子集）
                if len(target_cols) < len(source_columns):
                    logger.debug(
                        "[find_target_columns] Stage 1: 跳过（目标列数不足: %d < %d）",
                        len(target_cols), len(source_columns)
                    )
                    continue

                # 使用穷举排列算法匹配
                matched = self._match_columns_as_set(
                    source_columns=source_columns,
                    target_columns=target_cols,
                    source_profiles=source_profiles,
                    target_profiles=target_profiles,
                    min_name_similarity=self.composite_name_similarity_important_target,
                    min_type_compatibility=self.composite_min_type_compatibility,
                    source_is_physical=(combo_type == "physical"),  # 源表物理约束（PK/UK）
                    # 目标侧 Stage 1：统一视为“特权候选”，不做语义角色过滤（PK/UK/UCCs/索引）
                    target_is_physical=True
                )

                if matched:
                    logger.debug(
                        "[find_target_columns] Stage 1 成功: %s -> %s",
                        source_columns, matched
                    )
                    return matched

            logger.debug(
                "[find_target_columns] %s%s → %s: Stage 1 未找到匹配",
                source_table_name, source_columns, target_table_name
            )

        # ============================================================
        # Stage 2: 动态同名匹配（Dynamic Same-Name）
        # ============================================================
        # ⚠️ 修改：扩展到物理约束（PK/UK）+ 逻辑主键
        # 原因：逻辑主键也需要动态同名匹配来发现维度表→事实表的外键关系
        if combo_type in ["physical", "logical"]:
            logger.debug(
                "[find_target_columns] %s%s → %s: Stage 2 开始（combo_type=%s）",
                source_table_name, source_columns, target_table_name, combo_type
            )

            matched = self._find_dynamic_same_name(
                source_columns,
                source_table,
                target_table,
                is_physical=True  # 统一不过滤目标列，支持匹配外键
            )

            if matched:
                logger.debug(
                    "[find_target_columns] %s%s → %s: Stage 2 成功 %s",
                    source_table_name, source_columns, target_table_name, matched
                )
                return matched

            logger.debug(
                "[find_target_columns] %s%s → %s: Stage 2 未找到匹配",
                source_table_name, source_columns, target_table_name
            )
        else:
            logger.debug(
                "[find_target_columns] %s%s → %s: 跳过 Stage 2（combo_type=%s）",
                source_table_name, source_columns, target_table_name, combo_type
            )

        return None

    def _match_columns_as_set(
            self,
            source_columns: List[str],
            target_columns: List[str],
            source_profiles: Dict[str, dict],
            target_profiles: Dict[str, dict],
            min_name_similarity: float,
            min_type_compatibility: float,
            source_is_physical: bool = False,  # 新增：源表是否为物理约束（仅 PK/UK）
            target_is_physical: bool = False   # 新增：目标表是否为物理约束（PK/UK/索引）
    ) -> Optional[List[str]]:
        """穷举排列算法：在目标列中找到最佳匹配

        使用O(n! × n)的穷举排列算法，尝试所有可能的排列组合，找到综合得分最高的匹配。
        适用于复合键（2-3列），穷举成本可接受（最多6种排列）。

        Args:
            source_columns: 源列列表（有序）
            target_columns: 目标列候选池（无序）
            source_profiles: 源列画像
            target_profiles: 目标列画像
            min_name_similarity: 最低名称相似度阈值
            min_type_compatibility: 最低类型兼容性阈值
            source_is_physical: 源表是否为物理约束（仅 PK/UK，不含索引）
            target_is_physical: 目标表是否为物理约束（PK/UK/索引，广义物理约束）

        Returns:
            最佳匹配的目标列列表（顺序与源列对应），如果没有满足阈值的匹配则返回None
        """
        # === 源表过滤：完全不过滤（尊重所有约束） ===
        # 核心原则：源列（物理约束 + 逻辑主键）在候选生成阶段完全不过滤
        # - 物理约束（PK/UK）：DBA 明确定义，完全尊重
        # - 逻辑主键：在元数据生成阶段已按 composite_exclude_roles 过滤，此处不再二次过滤
        filtered_source_columns = source_columns  # ✅ 不过滤，完全尊重约束定义

        logger.debug(
            "[match_columns_as_set] 源表列不过滤（source_is_physical=%s），直接使用: %s",
            source_is_physical, source_columns
        )

        # === 目标表过滤：区分物理约束和逻辑约束 ===
        filtered_target_columns = []
        for tgt_col in target_columns:
            tgt_profile = target_profiles.get(tgt_col, {})
            tgt_semantic_role = tgt_profile.get("semantic_analysis", {}).get("semantic_role")

            # 物理约束：完全不过滤（完全尊重 DBA 定义，包括 metric）
            # ⚠️ 注意：目标表物理约束包括 PK/UK/索引（广义物理约束）
            if target_is_physical:
                logger.debug(
                    "[match_columns_as_set] 目标列 %s (物理约束: PK/UK/索引) 不过滤，语义角色=%s",
                    tgt_col, tgt_semantic_role
                )
                # ✅ 物理约束不进行语义角色过滤，直接通过
                pass
            # 逻辑约束：按配置排除
            else:
                if tgt_semantic_role in self.composite_exclude_semantic_roles:
                    logger.debug(
                        "[match_columns_as_set] 目标列 %s (逻辑约束) 语义角色=%s 被排除",
                        tgt_col, tgt_semantic_role
                    )
                    continue  # 跳过该列

            filtered_target_columns.append(tgt_col)

        # 验证：确保没有把所有列都过滤掉
        if not filtered_target_columns:
            logger.debug("[match_columns_as_set] 目标列全部被过滤，匹配失败")
            return None
        
        n = len(filtered_source_columns)
        m = len(filtered_target_columns)

        # 基本检查：目标列数量必须 >= 源列数量
        if m < n:
            return None

        if m == n:
            candidate_pools = [filtered_target_columns]
        else:
            candidate_pools = [list(c) for c in combinations(filtered_target_columns, n)]
            logger.debug(
                "[match_columns_as_set] 目标列数量(%d) > 源列数量(%d)，尝试子集数量=%d",
                m, n, len(candidate_pools)
            )

        best_match = None
        best_score = -1.0

        # 穷举所有排列（必要时先穷举子集）
        for pool in candidate_pools:
            for perm in permutations(pool):
                # perm 是一个元组，表示目标列的一种排列顺序
                perm_list = list(perm)

                # 逐对检查，任一配对低于阈值立即淘汰该排列
                total_name_sim = 0.0
                total_type_compat = 0.0
                is_valid = True  # 标记该排列是否有效

                for src_col, tgt_col in zip(filtered_source_columns, perm_list):
                    # 1. 名称相似度
                    name_sim = self._calculate_name_similarity(src_col, tgt_col)

                    # 2. 类型兼容性
                    src_profile = source_profiles.get(src_col, {})
                    tgt_profile = target_profiles.get(tgt_col, {})

                    src_type = src_profile.get("data_type", "")
                    tgt_type = tgt_profile.get("data_type", "")

                    type_compat = get_type_compatibility_score(src_type, tgt_type)

                    # 🔴 关键修改：任一配对低于阈值，立即淘汰该排列
                    if name_sim < min_name_similarity or type_compat < min_type_compatibility:
                        is_valid = False
                        logger.debug(
                            "[match_columns_as_set] 排列淘汰: %s->%s (name_sim=%.2f < %.2f 或 type_compat=%.2f < %.2f)",
                            src_col, tgt_col, name_sim, min_name_similarity,
                            type_compat, min_type_compatibility
                        )
                        break  # 立即跳出，不再检查该排列的其他配对

                    total_name_sim += name_sim
                    total_type_compat += type_compat

                # 只有所有配对都满足阈值，才计算综合得分
                if is_valid:
                    avg_name_sim = total_name_sim / n
                    avg_type_compat = total_type_compat / n
                    # 计算综合得分（简单加权：名称50% + 类型50%）
                    composite_score = 0.5 * avg_name_sim + 0.5 * avg_type_compat

                    # 更新最佳匹配
                    if composite_score > best_score:
                        best_score = composite_score
                        best_match = perm_list

        if best_match:
            logger.debug(
                "[match_columns_as_set] 找到最佳匹配: %s -> %s, score=%.3f",
                filtered_source_columns, best_match, best_score
            )
        else:
            logger.debug(
                "[match_columns_as_set] 未找到满足阈值的匹配: %s",
                filtered_source_columns
            )

        return best_match

    def _find_dynamic_same_name(
            self,
            source_columns: List[str],
            source_table: dict,
            target_table: dict,
            is_physical: bool = False  # 新增参数：是否为源表物理约束（PK/UK）
    ) -> Optional[List[str]]:
        """动态同名匹配（大小写不敏感 + 类型兼容）

        Args:
            source_columns: 源列列表
            source_table: 源表元数据
            target_table: 目标表元数据
            is_physical: 是否为源表物理约束（PK/UK）
                        - True：完全不过滤源表和目标表的列
                        - False：按配置过滤（但实际上不会调用，因为只对物理约束执行）

        Returns:
            目标列列表（保持源列顺序），未找到返回None

        ⚠️ 注意：此函数只在源表为物理约束（PK/UK）时调用
        """
        source_profiles = source_table.get("column_profiles", {})
        target_profiles = target_table.get("column_profiles", {})

        # === 源表：完全不过滤（移除原有的过滤代码） ===
        logger.debug(
            "[_find_dynamic_same_name] 源表物理约束（PK/UK）列不过滤: %s",
            source_columns
        )

        # === 目标表：源表为物理约束时，目标表完全不过滤 ===
        # ⚠️ 前提：此时源表必为物理约束（PK/UK），is_physical=True
        target_column_map = {}
        for col_name, col_profile in target_profiles.items():
            semantic_role = col_profile.get("semantic_analysis", {}).get("semantic_role")

            # 源表为物理约束：目标表任何列都可以作为候选，完全不过滤语义角色
            if is_physical:
                target_column_map[col_name.lower()] = col_name
                logger.debug(
                    "[_find_dynamic_same_name] 目标列 %s 不过滤（源为物理约束），语义角色=%s",
                    col_name, semantic_role
                )
            # 非物理约束：按配置过滤（实际上不会执行到这里）
            else:
                if semantic_role in self.composite_exclude_semantic_roles:
                    logger.debug(
                        "[_find_dynamic_same_name] 跳过目标列 %s（语义角色=%s）",
                        col_name, semantic_role
                    )
                    continue
                target_column_map[col_name.lower()] = col_name

        matched = []

        for src_col in source_columns:
            src_col_lower = src_col.lower()
            src_profile = source_profiles.get(src_col, {})

            # 大小写不敏感的同名检查
            if src_col_lower not in target_column_map:
                return None

            # 获取目标列的原始名称
            tgt_col = target_column_map[src_col_lower]
            tgt_profile = target_profiles.get(tgt_col, {})

            # 3. 类型兼容性检查
            src_type = src_profile.get("data_type", "")
            tgt_type = tgt_profile.get("data_type", "")

            # 使用类型兼容性评分（与 scorer 一致）
            type_score = get_type_compatibility_score(src_type, tgt_type)
            if type_score < self.composite_min_type_compatibility:
                logger.debug(
                    "[composite_dynamic_same_name] 类型兼容性不足: %s vs %s, score=%.2f < %.2f",
                    src_col, tgt_col, type_score, self.composite_min_type_compatibility
                )
                return None

            matched.append(tgt_col)

        return matched if len(matched) == len(source_columns) else None

    def _is_type_compatible(self, type1: str, type2: str) -> bool:
        """检查两个类型是否兼容

        复用共享模块的类型兼容性逻辑，返回布尔值（>= 0.5 视为兼容）

        Args:
            type1: 类型1
            type2: 类型2

        Returns:
            True 如果兼容，False 否则
        """
        return get_type_compatibility_score(type1, type2) >= 0.5

    def _generate_single_column_candidates(self, tables: Dict[str, dict]) -> List[Dict[str, Any]]:
        """生成单列候选
        
        统一逻辑：
        1. 源列必须是"重要列"（有定义约束 或 是逻辑主键）
        2. 遍历所有目标列，根据目标列是否"关键字段"动态调整名称相似度阈值
        3. 根据源列属性标记候选类型
        """
        candidates = []

        for source_name, source_table in tables.items():
            source_info = source_table.get("table_info", {})
            source_schema = source_info.get("schema_name")
            source_table_name = source_info.get("table_name")
            source_full_name = f"{source_schema}.{source_table_name}"
            logger.debug("[single_column_candidate] 处理源表: %s", source_full_name)
            source_profiles = source_table.get("column_profiles", {})

            for col_name, col_profile in source_profiles.items():
                # === 核心修改：先检查约束类型，不再提前过滤语义角色 ===
                # 1. 先检查源列是否"重要"（有定义约束 或 是逻辑主键）
                has_defined_constraint = self._has_defined_constraint(col_profile)
                is_logical_pk = self._is_logical_primary_key(col_name, source_table)

                # 源列必须至少满足一个条件
                if not (has_defined_constraint or is_logical_pk):
                    continue

                # 2. 源列完全不过滤（移除语义角色过滤逻辑）
                semantic_role = col_profile.get("semantic_analysis", {}).get("semantic_role")

                # ⚠️ 核心原则：源列完全不过滤
                # - 物理约束（PK/UK）：DBA 明确定义，完全尊重
                # - 逻辑主键：在元数据生成阶段已按 single_column_exclude_roles 过滤，此处不再二次过滤

                logger.debug(
                    "[single_column_candidate] 源列不过滤: %s.%s (physical=%s, logical=%s, role=%s)",
                    source_full_name, col_name, has_defined_constraint, is_logical_pk, semantic_role
                )
                
                # 3. 遍历所有目标表和目标列
                for target_name, target_table in tables.items():
                    if target_name == source_name:
                        continue

                    target_info = target_table.get("table_info", {})
                    target_schema = target_info.get("schema_name")
                    target_table_name = target_info.get("table_name")
                    target_profiles = target_table.get("column_profiles", {})

                    for target_col_name, target_col_profile in target_profiles.items():
                        # (a) 语义角色过滤：区分物理约束和逻辑约束
                        target_role = target_col_profile.get("semantic_analysis", {}).get("semantic_role")
                        target_structure_flags = target_col_profile.get("structure_flags", {})

                        # 检查外键表候选列是否有物理约束或索引（强信号）
                        target_has_physical = (
                            target_structure_flags.get("is_primary_key") or          # ✅ PK
                            target_structure_flags.get("is_unique_constraint") or    # ✅ UK（物理约束）
                            target_structure_flags.get("is_indexed") or              # ✅ 单列索引
                            target_structure_flags.get("is_composite_indexed_member")# ✅ 复合索引成员
                        )

                        # 外键表候选字段过滤优先级（从高到低）：
                        # 1. 物理约束或索引：不过滤语义角色（强约束/强信号）
                        # 2. 同名列：不过滤语义角色（强关联信号）
                        # 3. 其他列：按 exclude_semantic_roles 配置过滤（包括 complex）
                        if target_has_physical:
                            logger.debug(
                                "[single_column_candidate] 优先级1: 外键表列为物理约束/索引，不过滤: %s.%s (role=%s, flags=%s)",
                                f"{target_schema}.{target_table_name}", target_col_name, target_role,
                                {k: v for k, v in target_structure_flags.items() if v}
                            )
                            # ✅ 优先级1: 物理约束/索引不过滤，直接通过
                            pass
                        elif col_name.lower() == target_col_name.lower():
                            logger.debug(
                                "[single_column_candidate] 优先级2: 同名列不过滤: %s.%s (role=%s)",
                                f"{target_schema}.{target_table_name}", target_col_name, target_role
                            )
                            # ✅ 优先级2: 同名列不过滤（包括 complex 类型）
                            pass
                        else:
                            # ✅ 优先级3: 其他语义角色按配置过滤
                            if target_role in self.exclude_semantic_roles:
                                logger.debug(
                                    "[single_column_candidate] 优先级3: 跳过外键表列 %s.%s，语义角色=%s 被配置排除",
                                    f"{target_schema}.{target_table_name}", target_col_name, target_role
                                )
                                continue
                            logger.debug(
                                "[single_column_candidate] 优先级3: 外键表列通过过滤: %s.%s (role=%s)",
                                f"{target_schema}.{target_table_name}", target_col_name, target_role
                            )

                        # (b) 类型兼容性过滤
                        src_type = col_profile.get("data_type", "")
                        tgt_type = target_col_profile.get("data_type", "")
                        type_compat = get_type_compatibility_score(src_type, tgt_type)

                        if type_compat < self.single_min_type_compatibility:
                            logger.debug(
                                "[single_column_candidate] 跳过目标列 %s.%s -> %s.%s，类型兼容性不足: %.2f < %.2f",
                                source_full_name,
                                col_name,
                                f"{target_schema}.{target_table_name}",
                                target_col_name,
                                type_compat,
                                self.single_min_type_compatibility,
                            )
                            continue
                        
                        # (c) 判断目标列是否"关键字段"
                        is_important_target = self._is_qualified_target_column(
                            target_col_name, target_col_profile, target_table
                        )
                        
                        # (d) 名称相似度 + 动态阈值
                        name_sim = self._calculate_name_similarity(col_name, target_col_name)

                        if is_important_target:
                            threshold = self.single_name_similarity_important_target
                        else:
                            threshold = self.name_similarity_normal_target
                        
                        if name_sim < threshold:
                            logger.debug(
                                "[single_column_candidate] 跳过目标列 %s.%s -> %s.%s，名称相似度不足: %.2f < %.2f (important_target=%s)",
                                source_full_name,
                                col_name,
                                f"{target_schema}.{target_table_name}",
                                target_col_name,
                                name_sim,
                                threshold,
                                is_important_target,
                            )
                            continue
                        
                        # (e) FK 去重
                        fk_sig = self._make_signature(
                            source_schema, source_table_name, [col_name],
                            target_schema, target_table_name, [target_col_name]
                        )
                        if fk_sig in self.fk_signature_set:
                            logger.debug(
                                "[single_column_candidate] 跳过已存在的FK: %s.%s -> %s.%s",
                                source_full_name,
                                col_name,
                                f"{target_schema}.{target_table_name}",
                                target_col_name,
                            )
                            continue
                        
                        # (f) 决定 candidate_type
                        if has_defined_constraint and is_logical_pk:
                            candidate_type = "single_defined_constraint_and_logical_pk"
                        elif has_defined_constraint and not is_logical_pk:
                            candidate_type = "single_defined_constraint"
                        elif is_logical_pk and not has_defined_constraint:
                            candidate_type = "single_logical_key"
                        else:
                            # 理论上不会到这里（外层已经确保至少满足一个条件）
                            logger.warning(
                                "[single_column_candidate] 意外情况: %s.%s 既无定义约束也非逻辑主键，跳过",
                                source_full_name,
                                col_name,
                            )
                            continue
                        
                        # (g) 构造并追加候选
                        candidate = {
                            "source": source_table,
                            "target": target_table,
                            "source_columns": [col_name],
                            "target_columns": [target_col_name],
                            "candidate_type": candidate_type,
                        }
                        candidates.append(candidate)
                        logger.debug(
                            "[single_column_candidate] 候选生成: %s.%s -> %s.%s (type=%s, name_sim=%.2f, type_compat=%.2f)",
                            source_full_name,
                            col_name,
                            f"{target_schema}.{target_table_name}",
                            target_col_name,
                            candidate_type,
                            name_sim,
                            type_compat,
                        )

        return candidates

    def _has_defined_constraint(self, col_profile: dict) -> bool:
        """检查列是否有重要约束（用于驱动表侧的准入）"""
        structure_flags = col_profile.get("structure_flags", {})

        # 检查单列主键
        if structure_flags.get("is_primary_key"):
            if "single_field_primary_key" in self.important_constraints:
                return True

        # 检查单列唯一约束（只认物理唯一约束，不认统计唯一）
        if structure_flags.get("is_unique_constraint"):
            if "single_field_unique_constraint" in self.important_constraints:
                return True

        return False

    def _is_logical_primary_key(self, col_name: str, table: dict) -> bool:
        """检查列是否为逻辑主键（单列）"""
        table_profile = table.get("table_profile", {})
        unique_column_sets = table_profile.get("unique_column_sets", [])

        for lk in unique_column_sets:
            lk_cols = lk.get("columns", [])
            lk_conf = lk.get("confidence_score", 0)

            # 单列逻辑主键且置信度足够
            if len(lk_cols) == 1 and lk_cols[0] == col_name and lk_conf >= self.single_logical_key_min_confidence:
                return True

        return False

    def _is_qualified_target_column(self, col_name: str, col_profile: dict, table: dict) -> bool:
        """检查目标列是否满足单列候选的约束条件

        按照文档要求，目标列必须满足以下条件之一：
        1. structure_flags.is_primary_key = true （物理主键）
        2. structure_flags.is_unique_constraint = true （物理唯一约束）
        3. 在 unique_column_sets 的任一候选组合中（单列且 confidence_score >= 0.8）

        Args:
            col_name: 列名
            col_profile: 列画像
            table: 表元数据

        Returns:
            True 如果满足条件，False 否则
        """
        structure_flags = col_profile.get("structure_flags", {})

        # 1. 检查物理主键
        if structure_flags.get("is_primary_key"):
            return True

        # 2. 检查唯一约束（只认物理唯一约束，不认统计唯一）
        if structure_flags.get("is_unique_constraint"):
            return True

        # 3. 检查是否为单列逻辑主键（confidence >= 0.8）
        if self._is_logical_primary_key(col_name, table):
            return True

        return False

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """计算列名相似度（0-1，大小写不敏感）"""
        if self.name_similarity_service:
            return self.name_similarity_service.compare_pair(name1, name2)
        if name1.lower() == name2.lower():
            return 1.0

        # 使用SequenceMatcher
        return SequenceMatcher(None, name1.lower(), name2.lower()).ratio()

    def _make_signature(
            self,
            source_schema: str,
            source_table: str,
            source_columns: List[str],
            target_schema: str,
            target_table: str,
            target_columns: List[str]
    ) -> str:
        """生成FK签名（用于去重）"""
        src_cols = sorted(source_columns)
        tgt_cols = sorted(target_columns)
        return (
            f"{source_schema}.{source_table}.[{','.join(src_cols)}]->"
            f"{target_schema}.{target_table}.[{','.join(tgt_cols)}]"
        )
