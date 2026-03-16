"""Step 4 CQL 生成器

主生成器类，协调整个 Cypher 生成流程。
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, Any

from metaweave.core.cql_generator.models import CQLGenerationResult
from metaweave.core.cql_generator.reader import JSONReader
from metaweave.core.cql_generator.writer import CypherWriter
from metaweave.utils.file_utils import get_project_root

logger = logging.getLogger("metaweave.cql_generator")


class CQLGenerator:
    """CQL 生成器

    负责整体流程：
    1. 加载配置
    2. 读取 Step 2 和 Step 3 的 JSON 文件
    3. 生成 Cypher 脚本文件
    """

    def __init__(self, config_path: Path, domain_resolver=None):
        """初始化生成器

        Args:
            config_path: 配置文件路径
            domain_resolver: DomainResolver 实例，用于从 YAML 获取 table_domains
        """
        self.domain_resolver = domain_resolver
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        self.config = self._load_config()
        logger.info(f"加载配置: {self.config_path}")

        # 解析配置路径
        self.json_dir = self._resolve_path(
            self.config.get("output", {}).get("json_directory", "output/json")
        )
        self.rel_dir = self._resolve_path(
            self.config.get("output", {}).get("rel_directory", "output/rel")
        )
        self.cql_dir = self._resolve_path(
            self.config.get("output", {}).get("cql_directory", "output/cql")
        )

        logger.info(f"JSON 目录: {self.json_dir}")
        logger.info(f"关系目录: {self.rel_dir}")
        logger.info(f"CQL 输出目录: {self.cql_dir}")

    def _load_config(self) -> Dict[str, Any]:
        """加载 YAML 配置文件"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise

    def _resolve_path(self, path_str: str) -> Path:
        """解析路径（支持相对路径和绝对路径）"""
        path = Path(path_str)
        if not path.is_absolute():
            # 相对于项目根目录
            # 注意：迁移后配置文件位于 <project_root>/configs/metadata_config.yaml，
            # 不再是 <project_root>/configs/metaweave/metadata_config.yaml，
            # 因此不能再用 parent.parent.parent 这类固定层级推断。
            path = get_project_root() / path
        return path

    def generate(self, step_name: str = "cql") -> CQLGenerationResult:
        """执行 CQL 生成

        Args:
            step_name: 执行的步骤名称（"cql" 或 "cql_llm"），用于元数据记录

        Returns:
            生成结果
        """
        try:
            logger.info("=" * 60)
            logger.info("开始 Step 4: Neo4j CQL 生成")
            logger.info("=" * 60)

            # 1. 读取 JSON 数据
            logger.info("\n[1/2] 读取 Step 2 和 Step 3 的 JSON 文件...")
            reader = JSONReader(self.json_dir, self.rel_dir, domain_resolver=self.domain_resolver)
            tables, columns, has_column_rels, join_on_rels = reader.read_all()

            logger.info(f"  - 表节点: {len(tables)}")
            logger.info(f"  - 列节点: {len(columns)}")
            logger.info(f"  - HAS_COLUMN 关系: {len(has_column_rels)}")
            logger.info(f"  - JOIN_ON 关系: {len(join_on_rels)}")

            # 2. 生成 Cypher 文件
            logger.info("\n[2/2] 生成 Cypher 脚本文件...")
            writer = CypherWriter(self.cql_dir)
            output_files = writer.write_all(
                tables, columns, has_column_rels, join_on_rels
            )

            logger.info(f"  - 生成文件: {len(output_files)} 个")
            for file_path in output_files:
                logger.info(f"    * {file_path}")

            # 3. 生成元数据文档
            logger.info("\n[额外] 生成元数据文档...")

            # ✅ 实施时建议：添加调试日志确认数据可用性
            logger.debug(f"has_column_rels count: {len(has_column_rels)}")
            logger.debug(f"join_on_rels count: {len(join_on_rels)}")
            logger.debug("Calling write_metadata after write_all")

            # ✅ 保护主流程：元数据生成失败不应影响 CQL 生成
            errors = []
            try:
                metadata_file = writer.write_metadata(
                    tables=tables,
                    columns=columns,
                    has_column_rels=has_column_rels,
                    join_on_rels=join_on_rels,
                    step_name=step_name,
                    json_dir=self.json_dir,
                    rel_dir=self.rel_dir
                )
                logger.info(f"  - 元数据文档: {metadata_file}")
                output_files.append(str(metadata_file))
            except Exception as e:
                error_msg = f"元数据文档生成失败: {e}"
                logger.warning(f"{error_msg}（不影响主流程）")
                errors.append(error_msg)

            # 构造结果
            result = CQLGenerationResult(
                success=True,
                output_files=output_files,
                tables_count=len(tables),
                columns_count=len(columns),
                has_column_count=len(has_column_rels),
                relationships_count=len(join_on_rels),
                errors=errors
            )

            logger.info("\n" + "=" * 60)
            logger.info("✅ Step 4 完成")
            logger.info("=" * 60)
            logger.info(str(result))

            return result

        except Exception as e:
            logger.error(f"CQL 生成失败: {e}", exc_info=True)
            return CQLGenerationResult(
                success=False,
                output_files=[],
                tables_count=0,
                columns_count=0,
                relationships_count=0,
                errors=[str(e)]
            )
