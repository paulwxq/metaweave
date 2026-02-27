"""dim_tables 配置生成 CLI 命令。"""

from pathlib import Path

import click

from metaweave.core.dim_value.config_generator import DimTableConfigGenerator
from metaweave.utils.file_utils import get_project_root, load_yaml


@click.command(name="dim_config")
@click.option(
    "--generate",
    "-g",
    "generate",
    is_flag=True,
    required=True,
    help="生成 dim_tables.yaml 配置文件",
)
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    default="configs/metadata_config.yaml",
    show_default=True,
    help="metadata_config.yaml 路径",
)
@click.option(
    "--output",
    "-o",
    "output_path",
    type=click.Path(),
    default="configs/dim_tables.yaml",
    show_default=True,
    help="输出 dim_tables.yaml 路径",
)
def dim_config_command(generate: bool, config_path: str, output_path: str) -> None:
    """生成 dim_tables.yaml（识别 table_category='dim' 的表）。"""

    if not generate:
        click.echo("❌ 请提供 --generate 选项")
        raise click.Abort()

    project_root = get_project_root()
    metadata_path = Path(config_path)
    if not metadata_path.is_absolute():
        metadata_path = project_root / metadata_path

    output_path = Path(output_path)
    if not output_path.is_absolute():
        output_path = project_root / output_path

    metadata_config = load_yaml(metadata_path)
    output_cfg = metadata_config.get("output", {}) if metadata_config else {}
    json_dir = output_cfg.get("json_directory")
    if not json_dir:
        click.echo("❌ metadata_config.yaml 缺少 output.json_directory 配置")
        raise click.Abort()

    json_dir = Path(json_dir)
    if not json_dir.is_absolute():
        json_dir = project_root / json_dir

    # 开始扫描前先打印日志
    click.echo("")
    click.echo("🔍 开始扫描维度表...")
    click.echo(f"📂 扫描目录: {json_dir}")
    click.echo("")

    generator = DimTableConfigGenerator(json_dir=json_dir, output_path=output_path)
    config = generator.generate()

    databases_cfg = config.get("databases", {})
    total_tables = sum(
        len(db_cfg.get("tables", {}))
        for db_cfg in databases_cfg.values()
        if isinstance(db_cfg, dict)
    )

    click.echo(f"✅ 已生成 {output_path}")
    click.echo(f"📊 识别到 {len(databases_cfg)} 个数据库，{total_tables} 个维度表：")
    for db_name, db_cfg in databases_cfg.items():
        tables = db_cfg.get("tables", {}) if isinstance(db_cfg, dict) else {}
        click.echo(f"  - {db_name} ({len(tables)} 张)")
        for table_name in tables.keys():
            click.echo(f"      - {table_name}")

    click.echo("")
    click.echo("⚠️  请手工填写 embedding_col 字段（要向量化的列名）")
    click.echo("")
    if databases_cfg:
        first_db_name = next(iter(databases_cfg.keys()))
        first_tables = databases_cfg[first_db_name].get("tables", {}) if isinstance(databases_cfg[first_db_name], dict) else {}
        sample_table = next(iter(first_tables.keys()), "public.dim_example")
        click.echo("📝 配置示例：")
        click.echo("    databases:")
        click.echo(f"      {first_db_name}:")
        click.echo("        tables:")
        click.echo(f"          {sample_table}:")
        click.echo("            embedding_col: your_text_column       # 单列")
        click.echo("")
        click.echo("    # 多列向量化（同一张表的多个列）：")
        click.echo("    databases:")
        click.echo(f"      {first_db_name}:")
        click.echo("        tables:")
        click.echo(f"          {sample_table}:")
        click.echo("            embedding_col: [col1, col2, col3]     # YAML列表（推荐）")
        click.echo("            # 或")
        click.echo("            embedding_col: col1, col2, col3       # 逗号分隔（自动拆分）")


__all__ = ["dim_config_command"]
