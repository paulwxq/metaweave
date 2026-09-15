# Rel 评分五维化与 Embedding 模型切换设计

## 1. 需求

1. 评分由四维改为五维，增加独立维度 `name_similarity`。
2. 权重：

   | 维度 | 权重 |
   |---|---|
   | `inclusion_rate` | 0.40 |
   | `name_similarity` | 0.10 |
   | `comment_similarity` | 0.10 |
   | `type_compatibility` | 0.20 |
   | `jaccard_index` | 0.20 |

3. embedding 模型改为 `qwen3.7-text-embedding`。

## 2. 修改的代码模块

| 模块 | 文件 | 修改内容 |
|---|---|---|
| 配置 | `configs/metadata_config.yaml` | `embedding.providers.qwen.model` 改为 `qwen3.7-text-embedding`，按新模型输出更新 `dimensions`；`relationships.weights` 改为上表五维 |
| 评分 | `metaweave/core/relationships/scorer.py` | `DEFAULT_WEIGHTS` 改为五维；`_calculate_scores` 把 `name_similarity` 写入 `score_details`；`comment_similarity` 不再回退到名称相似度（注释不可用或通道关闭时用 `comment_fallback_score`）；键校验/报错文案改为五维 |
| 数据模型 | `metaweave/core/relationships/models.py` | `score_details` 注释改为五维 |
| 单测 | `tests/unit/metaweave/relationships/test_scorer.py` | 夹具 weights 改为五维；名称维独立计分；注释缺失或通道关闭时 comment 用 fallback，name 单独计 |
| 单测 | `tests/unit/metaweave/relationships/test_writer.py` | 夹具 `weights` 与样例 `score_details` 补 `name_similarity` |
| 单测 | 其它写死四维 weights 的用例 | 按编译失败补齐 |

`name_similarity.py` 的 `EmbeddingService` 读全局 embedding 配置，改 YAML 即切换模型，不改该模块代码。

## 3. 修改步骤

1. 改 `configs/metadata_config.yaml`：`model`、`dimensions`、`weights`。
2. 改 `scorer.py`：`DEFAULT_WEIGHTS`；`_calculate_scores` 增加 `name_similarity`；`_score_comment_pair` 去掉对 `_calculate_name_similarity` 的回退。
3. 改 `models.py` 中 `score_details` 注释。
4. 改 `test_scorer.py`、`test_writer.py` 及其它四维夹具。
5. 跑 `pytest tests/`。
