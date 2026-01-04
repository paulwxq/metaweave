"""元数据生成器

协调整个元数据生成流程的主控制器。
"""

import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from metaweave.core.metadata.connector import DatabaseConnector
from metaweave.core.metadata.ddl_loader import DDLLoader, DDLLoaderError
from metaweave.core.metadata.extractor import MetadataExtractor
from metaweave.core.metadata.comment_generator import CommentGenerator
from metaweave.core.metadata.logical_key_detector import LogicalKeyDetector
from metaweave.core.metadata.formatter import OutputFormatter
from metaweave.core.metadata.models import GenerationResult, TableMetadata
from metaweave.core.metadata.profiler import MetadataProfiler
from metaweave.services.llm_service import LLMService
from metaweave.utils.file_utils import get_project_root
from metaweave.utils.data_utils import get_column_statistics
from services.config_loader import ConfigLoader

logger = logging.getLogger("metaweave.generator")
SUPPORTED_STEPS = {"ddl", "json", "cql", "md"}


class MetadataGenerator:
    """元数据生成器
    
    协调整个元数据生成流程，包括：
    1. 连接数据库
    2. 提取元数据
    3. 数据采样
    4. LLM 生成注释
    5. 识别逻辑主键
    6. 格式化输出
    """
    
    def __init__(self, config_path: str | Path):
        """初始化元数据生成器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        # 初始化各个组件
        self._init_components()
        
        logger.info("元数据生成器已初始化")
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件（使用 ConfigLoader 处理环境变量替换）"""
        try:
            config_loader = ConfigLoader(str(self.config_path))
            config = config_loader.load()
            if not config:
                raise ValueError(f"配置文件加载失败: {self.config_path}")
            logger.info(f"配置文件加载成功: {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise
    
    def _init_components(self):
        """初始化所有组件"""
        # 数据库连接器（延迟初始化，md 步骤不需要）
        db_config = self.config.get("database", {})
        self.database_name = db_config.get("database")
        self.connector = None  # 延迟初始化，仅在需要时创建

        # 元数据提取器（延迟初始化）
        self.extractor = None
        
        # LLM 服务（如果启用）
        comment_config = self.config.get("comment_generation", {})
        self.comment_enabled = comment_config.get("enabled", True)
        
        if self.comment_enabled:
            llm_config = self.config.get("llm", {})
            try:
                self.llm_service = LLMService(llm_config)

                # 注释生成器（不使用本地 cache）
                self.comment_generator = CommentGenerator(self.llm_service)
            except Exception as e:
                logger.warning(f"LLM 服务初始化失败，注释生成将被禁用: {e}")
                self.comment_enabled = False
        
        # 逻辑主键检测器
        logical_key_config = self.config.get("logical_key_detection", {})
        self.logical_key_enabled = logical_key_config.get("enabled", True)
        if self.logical_key_enabled:
            # 从 single_column.exclude_semantic_roles 读取单列排除配置
            single_column_config = self.config.get("single_column", {})
            single_column_exclude_roles = single_column_config.get("exclude_semantic_roles", ["audit", "metric"])
            logical_key_config["single_column_exclude_roles"] = single_column_exclude_roles

            # === 新增：传递 composite 配置（与 CandidateGenerator 使用相同配置） ===
            composite_config = self.config.get("composite", {})
            # 默认值保守策略：只排除明确不适合的 metric
            composite_exclude_roles = composite_config.get("exclude_semantic_roles", ["metric"])
            logical_key_config["composite_exclude_roles"] = composite_exclude_roles

            logger.info(f"传递复合键排除角色配置给逻辑主键检测器: {composite_exclude_roles}")

            self.logical_key_detector = LogicalKeyDetector(logical_key_config)
        
        # 输出格式化器
        output_config = self.config.get("output", {})
        self.formatter = OutputFormatter(output_config, database_name=self.database_name)
        self.active_step = "ddl"
        self.active_formats = self.formatter.formats
        self.ddl_loader: Optional[DDLLoader] = None
        self.profiler = MetadataProfiler(self.config)
        
        # 采样配置
        self.sampling_config = self.config.get("sampling", {})
        self.sampling_enabled = self.sampling_config.get("enabled", True)
        self.sample_size = self.sampling_config.get("sample_size", 1000)
        
        # 列统计配置
        column_stats_config = self.sampling_config.get("column_statistics", {})
        self.column_stats_enabled = column_stats_config.get("enabled", True)
        self.value_dist_threshold = column_stats_config.get("value_distribution_threshold", 10)
        logger.info(f"列统计配置: enabled={self.column_stats_enabled}, threshold={self.value_dist_threshold}")

    def _ensure_connector(self):
        """延迟初始化数据库连接器（仅在需要时）"""
        if self.connector is None:
            db_config = self.config.get("database", {})
            self.connector = DatabaseConnector(db_config)
            self.extractor = MetadataExtractor(self.connector)
            logger.info("数据库连接器已延迟初始化")

    def _infer_schemas_from_ddl_dir(self) -> List[str]:
        """从 DDL 目录推断 schemas（用于 md 步骤）

        仅支持严格的 {database}.{schema}.{table}.sql 文件名格式。
        schema 或 table 名称包含特殊字符（如 '.'）的文件会被跳过并警告。

        Returns:
            schema 列表（去重）
        """
        ddl_dir = self.formatter.output_dir / "ddl"
        if not ddl_dir.exists():
            logger.warning(f"DDL 目录不存在: {ddl_dir}")
            return []

        # DDL 文件格式: {database}.{schema}.{table}.sql
        database_name = self.database_name
        pattern = f"{database_name}.*.*.sql"  # glob 用于粗过滤（匹配 db.*.*.sql）
        schemas = set()

        # 注意：glob 只是粗过滤，最终以 stem 校验为准
        for ddl_file in ddl_dir.glob(pattern):
            # 解析文件名 stem（去除 .sql）: store_db.public.employee
            parts = ddl_file.stem.split(".")
            if len(parts) == 3:  # 严格校验 stem 为 3 段：db.schema.table
                schema = parts[1]
                schemas.add(schema)
            else:
                logger.warning(f"DDL 文件 stem 格式异常，跳过: {ddl_file.name}（期望 stem 3 段，实际 {len(parts)} 段）")

        schema_list = sorted(schemas)
        logger.info(f"从 DDL 目录推断出 {len(schema_list)} 个 schema: {schema_list}")
        return schema_list

    def generate(
        self,
        schemas: Optional[List[str]] = None,
        tables: Optional[List[str]] = None,
        incremental: bool = False,
        max_workers: int = 4,
        step: str = "ddl"
    ) -> GenerationResult:
        """生成元数据
        
        Args:
            schemas: 指定要处理的 schema 列表，None 表示处理配置文件中的所有 schema
            tables: 指定要处理的表列表，None 表示处理所有表
            incremental: 是否增量更新模式（暂未实现）
            max_workers: 最大并发数
            
        Returns:
            生成结果
        """
        result = GenerationResult(success=True)
        self.active_step = self._normalize_step(step)
        self.active_formats = self._resolve_formats_for_step(self.active_step)
        logger.info(f"执行步骤: {self.active_step}")
        
        try:
            # 测试数据库连接（md 步骤跳过）
            if self.active_step != "md":
                self._ensure_connector()  # 延迟初始化
                if not self.connector.test_connection():
                    result.success = False
                    result.add_error("数据库连接失败")
                    return result
            else:
                logger.info("md 步骤跳过数据库连接（从 DDL 文件读取）")

            # 获取要处理的 schema 列表
            if schemas is None:
                schemas = self.config.get("database", {}).get("schemas", [])

            if not schemas:
                if self.active_step == "md":
                    # md 步骤：从 DDL 目录推断 schemas
                    schemas = self._infer_schemas_from_ddl_dir()
                    if not schemas:
                        result.success = False
                        result.add_error(
                            "md 步骤无法推断 schemas：DDL 目录为空且配置文件未指定 database.schemas\n"
                            "请在配置文件中设置 database.schemas 或先执行 --step ddl"
                        )
                        return result
                else:
                    self._ensure_connector()
                    schemas = self.connector.get_schemas()
            
            logger.info(f"将处理以下 schema: {schemas}")
            
            # 获取所有要处理的表
            all_tables = self._get_tables_to_process(schemas, tables)
            
            if not all_tables:
                logger.warning("没有找到需要处理的表")
                return result
            
            logger.info(f"共找到 {len(all_tables)} 张表待处理")
            
            # 并发处理表
            if max_workers > 1:
                result = self._process_tables_parallel(all_tables, max_workers, result)
            else:
                result = self._process_tables_sequential(all_tables, result)
            
            logger.info(f"元数据生成完成: 成功 {result.processed_tables} 张，失败 {result.failed_tables} 张")
            
        except Exception as e:
            logger.error(f"元数据生成过程出错: {e}")
            result.success = False
            result.add_error(str(e))
        
        finally:
            # 关闭数据库连接（防空检查）
            if self.connector is not None:
                self.connector.close()
        
        return result
    
    def _get_tables_from_ddl_dir(self, schema: str) -> List[str]:
        """从 DDL 目录扫描表名（用于 md 步骤）

        仅支持严格的 {database}.{schema}.{table}.sql 文件名格式。
        table 名称包含特殊字符（如 '.'）的文件会被跳过并警告。

        Args:
            schema: schema 名称

        Returns:
            表名列表
        """
        ddl_dir = self.formatter.output_dir / "ddl"
        if not ddl_dir.exists():
            logger.warning(f"DDL 目录不存在: {ddl_dir}")
            return []

        # DDL 文件格式: {database}.{schema}.{table}.sql
        database_name = self.database_name
        pattern = f"{database_name}.{schema}.*.sql"  # glob 用于粗过滤

        tables = []
        # 注意：glob 只是粗过滤，最终以 stem 校验为准
        for ddl_file in ddl_dir.glob(pattern):
            # 解析文件名 stem（去除 .sql）: store_db.public.employee → employee
            parts = ddl_file.stem.split(".")
            if len(parts) == 3:  # 严格校验 stem 为 3 段：db.schema.table
                table_name = parts[2]
                tables.append(table_name)
                logger.debug(f"从 DDL 文件发现表: {schema}.{table_name}")
            else:
                logger.warning(f"DDL 文件 stem 格式异常，跳过: {ddl_file.name}（期望 stem 3 段，实际 {len(parts)} 段）")

        logger.info(f"从 DDL 目录扫描到 {len(tables)} 张表: {schema}.*")
        return tables

    def _get_tables_to_process(
        self,
        schemas: List[str],
        tables: Optional[List[str]]
    ) -> List[tuple]:
        """获取要处理的表列表

        Args:
            schemas: schema 列表
            tables: 表名列表（可选）

        Returns:
            (schema, table) 元组列表
        """
        all_tables = []
        exclude_patterns = self.config.get("database", {}).get("exclude_tables", [])

        for schema in schemas:
            # md 步骤：从 DDL 目录枚举表
            if self.active_step == "md":
                schema_tables = self._get_tables_from_ddl_dir(schema)
            else:
                schema_tables = self.connector.get_tables(schema)
            
            for table in schema_tables:
                # 如果指定了表名列表，只处理列表中的表
                if tables and table not in tables:
                    continue
                
                # 检查是否在排除列表中
                excluded = False
                for pattern in exclude_patterns:
                    if pattern.endswith("*"):
                        prefix = pattern[:-1]
                        if table.startswith(prefix):
                            excluded = True
                            break
                    elif table == pattern:
                        excluded = True
                        break
                
                if not excluded:
                    all_tables.append((schema, table))
        
        return all_tables
    
    def _process_tables_sequential(
        self,
        tables: List[tuple],
        result: GenerationResult
    ) -> GenerationResult:
        """顺序处理表"""
        with tqdm(total=len(tables), desc="处理表") as pbar:
            for schema, table in tables:
                try:
                    self._process_table(schema, table, result)
                    result.processed_tables += 1
                except Exception as e:
                    logger.error(f"处理表失败 ({schema}.{table}): {e}")
                    result.failed_tables += 1
                    result.add_error(f"{schema}.{table}: {str(e)}")
                finally:
                    pbar.update(1)
        
        return result
    
    def _process_tables_parallel(
        self,
        tables: List[tuple],
        max_workers: int,
        result: GenerationResult
    ) -> GenerationResult:
        """并行处理表"""
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_table = {
                executor.submit(self._process_table, schema, table, result): (schema, table)
                for schema, table in tables
            }
            
            # 使用 tqdm 显示进度
            with tqdm(total=len(tables), desc="处理表") as pbar:
                for future in as_completed(future_to_table):
                    schema, table = future_to_table[future]
                    try:
                        future.result()
                        result.processed_tables += 1
                    except Exception as e:
                        logger.error(f"处理表失败 ({schema}.{table}): {e}")
                        result.failed_tables += 1
                        result.add_error(f"{schema}.{table}: {str(e)}")
                    finally:
                        pbar.update(1)
        
        return result
    
    def _process_table(
        self,
        schema: str,
        table: str,
        result: GenerationResult
    ):
        if self.active_step == "json":
            # json 步骤：从 DDL 读取，但执行 COUNT/采样/画像（需要数据库）
            self._process_table_from_ddl(schema, table, result)
        elif self.active_step == "md":
            # md 步骤：完全 file-only，不访问数据库
            self._process_table_from_ddl_for_md(schema, table, result)
        else:
            # ddl/rel 等其他步骤：直接查库
            self._process_table_from_db(schema, table, result)

    def _process_table_from_db(
        self,
        schema: str,
        table: str,
        result: GenerationResult
    ):
        """处理单张表
        
        Args:
            schema: schema 名称
            table: 表名
            result: 生成结果对象
        """
        logger.info(f"开始处理表: {schema}.{table}")
        
        try:
            # 1. 提取元数据
            metadata = self.extractor.extract_all(schema, table)
            if not metadata:
                raise ValueError(f"提取元数据失败: {schema}.{table}")
            
            # 设置数据库名称
            metadata.database = self.connector.database
            
            # 2. 数据采样
            sample_data = None
            ddl_only_mode = self.active_step == "ddl" and self.active_formats == ["ddl"]
            if self.sampling_enabled:
                if ddl_only_mode:
                    needs_sample_data = bool(self.comment_enabled) or bool(
                        getattr(self.formatter, "sample_record_options", {}).get("enabled", True)
                    )
                    if needs_sample_data:
                        sample_data = self._sample_data_for_ddl(schema, table)
                else:
                    sample_data = self.connector.sample_data(schema, table, self.sample_size)
                    self._apply_column_statistics(metadata, sample_data)
            
            # 3. 生成注释（如果启用）
            if self.comment_enabled:
                comment_count = self.comment_generator.enrich_metadata_with_comments(metadata, sample_data)
                result.generated_comments += comment_count
            
            if not ddl_only_mode:
                # 4. 生成列画像
                column_profiles = self.profiler._profile_columns(metadata, sample_data)
                metadata.column_profiles = column_profiles

                # 5. 生成逻辑主键（依赖列画像）
                if self.logical_key_enabled and metadata.column_profiles:
                    logical_keys = self.logical_key_detector.detect(metadata, sample_data)
                    metadata.candidate_logical_primary_keys = logical_keys
                    if logical_keys:
                        result.logical_keys_found += len(logical_keys)

                # 6. 生成表画像（依赖列画像+逻辑主键）
                table_profile = self.profiler._profile_table(metadata, column_profiles)
                metadata.table_profile = table_profile
            
            # 7. 格式化输出
            output_files = self.formatter.format_and_save(
                metadata,
                sample_data,
                formats_override=self.active_formats
            )
            for file_path in output_files.values():
                result.add_output_file(file_path)
            
            logger.info(f"表处理完成: {schema}.{table}")
            
        except Exception as e:
            # 记录详细的错误信息
            logger.error(f"处理表失败 ({schema}.{table}): {type(e).__name__}: {e}", exc_info=True)
            raise

    def _sample_data_for_ddl(self, schema: str, table: str):
        """用于 --step ddl 的轻量采样：优先取到 target_rows 条“非全空行”的记录。

        - 最终返回最多 target_rows 行
        - 会过滤掉“整行全是 NULL”的记录（如果存在）
        """
        try:
            target_rows = 5
            fetch_limit = target_rows * 2
            df = self.connector.sample_data(schema, table, fetch_limit)
            if df is None or df.empty:
                return df
            non_empty = df[df.notna().any(axis=1)]
            if non_empty.empty:
                return df.iloc[0:0]
            return non_empty.head(target_rows)
        except Exception as e:
            logger.warning(f"DDL 采样失败 ({schema}.{table}): {e}")
            return None

    def _process_table_from_ddl(
        self,
        schema: str,
        table: str,
        result: GenerationResult
    ):
        logger.info(f"开始处理表 (DDL): {schema}.{table}")
        try:
            parsed = self._get_ddl_loader().load_table(schema, table)
            metadata = parsed.metadata
            
            # 设置数据库名称（从 DDL loader 获取）
            metadata.database = self._get_ddl_loader().database_name
        except DDLLoaderError as exc:
            logger.error(f"DDL 解析失败 ({schema}.{table}): {exc}")
            result.failed_tables += 1
            result.add_error(f"{schema}.{table}: {exc}")
            return

        # 从数据库查询真实的行数（使用 COUNT(*) 获取精确值）
        try:
            count_sql = f"SELECT COUNT(*) as row_count FROM {schema}.{table}"
            query_result = self.connector.execute_query(count_sql, fetch_one=True)
            if query_result and len(query_result) > 0:
                metadata.row_count = query_result[0].get("row_count", 0)
                logger.info(f"✅ 更新行数: {schema}.{table} = {metadata.row_count}")
            else:
                logger.warning(f"⚠️ 未获取到行数: {schema}.{table}, row_count 保持为 0")
        except Exception as e:
            logger.warning(f"❌ 查询行数失败 ({schema}.{table}): {e}, 保持默认值 0")

        sample_data = None
        if self.sampling_enabled:
            sample_data = self.connector.sample_data(schema, table, self.sample_size)
            self._apply_column_statistics(metadata, sample_data)

        # 步骤1: 生成列画像
        column_profiles = self.profiler._profile_columns(metadata, sample_data)
        metadata.column_profiles = column_profiles

        # 步骤2: 生成逻辑主键（依赖列画像）
        if self.logical_key_enabled and metadata.column_profiles:
            logical_keys = self.logical_key_detector.detect(metadata, sample_data)
            metadata.candidate_logical_primary_keys = logical_keys
            if logical_keys:
                result.logical_keys_found += len(logical_keys)

        # 步骤3: 生成表画像（依赖列画像+逻辑主键）
        table_profile = self.profiler._profile_table(metadata, column_profiles)
        metadata.table_profile = table_profile

        output_files = self.formatter.format_and_save(
            metadata,
            sample_data,
            formats_override=self.active_formats
        )
        for file_path in output_files.values():
            result.add_output_file(file_path)

        logger.info(f"表处理完成 (JSON): {schema}.{table}")

    def _process_table_from_ddl_for_md(
        self,
        schema: str,
        table: str,
        result: GenerationResult
    ):
        """md 专用：从 DDL 文件生成 Markdown（file-only，不访问数据库）

        与 _process_table_from_ddl() 的区别：
        - 不执行 COUNT 查询（md 不展示行数）
        - 不执行列画像/逻辑主键/表画像（md 不需要）
        - 不采样数据库（使用 DDL 的 sample_records）
        - 完全 file-only，零数据库访问
        """
        logger.info(f"开始处理表 (Markdown): {schema}.{table}")

        # 1. 从 DDL 文件加载元数据
        try:
            parsed = self._get_ddl_loader().load_table(schema, table)
            metadata = parsed.metadata
            metadata.database = self.database_name
        except DDLLoaderError as exc:
            logger.error(f"DDL 解析失败 ({schema}.{table}): {exc}")
            result.failed_tables += 1
            result.add_error(f"{schema}.{table}: {exc}")
            return

        # 2. 将 DDL sample_records 转换为 DataFrame（仅用于注释生成辅助）
        sample_data = None
        if parsed.sample_records:
            import pandas as pd
            records_data = [rec.get("data", {}) for rec in parsed.sample_records if rec.get("data")]
            if records_data:
                sample_data = pd.DataFrame(records_data)
                logger.info(f"使用 DDL 样例数据: {schema}.{table}, {len(sample_data)} 行")
            else:
                logger.warning(f"DDL 样例数据为空: {schema}.{table}")
        else:
            logger.warning(f"DDL 无样例数据: {schema}.{table}")

        # 3. 补全缺失的注释（可选，使用 LLM + 缓存）
        if self.comment_enabled:
            comment_count = self.comment_generator.enrich_metadata_with_comments(
                metadata,
                sample_data  # 辅助 LLM 理解字段含义
            )
            if comment_count > 0:
                result.generated_comments += comment_count
                logger.info(f"补全注释: {schema}.{table}, {comment_count} 个")

        # 4. 跳过列统计、画像、逻辑主键（md 不需要）
        # 注意：
        # - md 输出不展示列统计信息
        # - md 输出不展示画像/逻辑主键
        # - 保持字段为空值，避免序列化错误
        metadata.column_profiles = {}
        metadata.candidate_logical_primary_keys = []
        metadata.table_profile = None

        # 5. 格式化输出（仅生成 markdown）
        output_files = self.formatter.format_and_save(
            metadata,
            sample_data,  # 用于提取示例值
            formats_override=["markdown"]  # 仅输出 md 格式
        )
        for file_path in output_files.values():
            result.add_output_file(file_path)

        # 注意：不需要 result.processed_tables += 1
        # 外层框架（_process_tables_sequential/parallel）已统计
        logger.info(f"Markdown 生成完成: {schema}.{table}")

    def _generate_summary(self, result: GenerationResult):
        """生成汇总报告"""
        summary_lines = []
        summary_lines.append("=" * 60)
        summary_lines.append("元数据生成汇总报告")
        summary_lines.append("=" * 60)
        summary_lines.append(f"成功处理: {result.processed_tables} 张表")
        summary_lines.append(f"处理失败: {result.failed_tables} 张表")
        summary_lines.append(f"生成注释: {result.generated_comments} 个")
        summary_lines.append(f"识别逻辑主键: {result.logical_keys_found} 个")
        summary_lines.append(f"输出文件: {len(result.output_files)} 个")
        
        if result.errors:
            summary_lines.append(f"\n错误列表:")
            for error in result.errors[:10]:  # 最多显示 10 个错误
                summary_lines.append(f"  - {error}")
            if len(result.errors) > 10:
                summary_lines.append(f"  ... 还有 {len(result.errors) - 10} 个错误")
        
        summary_lines.append("=" * 60)
        
        summary_text = "\n".join(summary_lines)
        logger.info(f"\n{summary_text}")
        
        # 保存汇总报告到文件
        try:
            from metaweave.utils.file_utils import save_text, ensure_dir
            from datetime import datetime
            
            output_dir = self.config.get("output", {}).get("output_dir", "output")
            output_dir = get_project_root() / output_dir
            ensure_dir(output_dir)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            summary_file = output_dir / f"summary_{timestamp}.txt"
            save_text(summary_text, summary_file)
            logger.info(f"汇总报告已保存: {summary_file}")
        except Exception as e:
            logger.error(f"保存汇总报告失败: {e}")

    def _get_ddl_loader(self) -> DDLLoader:
        if self.ddl_loader is None:
            ddl_dir = self.formatter.output_dir / "ddl"
            self.ddl_loader = DDLLoader(ddl_dir, database_name=self.database_name)
        return self.ddl_loader

    def _apply_column_statistics(self, metadata: TableMetadata, sample_data):
        if not self.column_stats_enabled or sample_data is None or sample_data.empty:
            return
        for col in metadata.columns:
            if col.column_name in sample_data.columns:
                col.statistics = get_column_statistics(
                    sample_data,
                    col.column_name,
                    value_distribution_threshold=self.value_dist_threshold,
                )
        logger.info(f"已计算 {len(metadata.columns)} 个字段的统计信息: {metadata.full_name}")

    def _normalize_step(self, step: str) -> str:
        """标准化步骤参数"""
        normalized = (step or "all").lower()
        if normalized not in SUPPORTED_STEPS:
            raise ValueError(f"不支持的步骤: {step}")
        return normalized

    def _resolve_formats_for_step(self, step: str) -> List[str]:
        """根据步骤确定需要输出的文件格式"""
        mapping = {
            "ddl": ["ddl"],
            "json": ["json"],
            "md": ["markdown"],
        }
        if step == "cql":
            logger.warning("CQL 生成尚未实现，暂不输出文件")
            return []
        return mapping.get(step, [])
