# MetaWeave

本目录是从 `nl2sql_v3/src/metaweave/` 复制迁移出来的独立项目（仅复制，不修改 `nl2sql_v3/`）。

## 开发环境（WSL）

本项目使用 `uv` 管理虚拟环境与依赖。请你手工创建 WSL 虚拟环境目录 `.venv-wsl`，我不会自动创建：

```bash
cd metaweave
uv venv .venv-wsl
uv sync
```

## CLI

```bash
cd metaweave
uv run metaweave --help
```
