# 1. LangChain 升级与 Agent 机制改造建议

日期：2026-09-10  
状态：可行性评估与讨论建议，尚未实施升级。

## 1. 结论与范围

建议升级现有 LangChain 模型调用层，并按实际需求引入工作流能力。当前不建议将 MetaWeave 主流程整体改造成 Deep Agents。

本文件仅讨论改造计划中的第一项：LangChain / LangGraph 升级，以及 Deep Agents、Middleware 等机制的适用性。Milvus 替换、Docker 部署、纯数据关系发现策略和 REST API 将另行讨论。

基于当前仓库的依赖与代码检查，**MetaWeave 尚未使用 LangGraph，也未发现自定义 ReAct Agent**。因此，引入 LangGraph 或 Deep Agents 属于新增架构能力，而非已有组件的版本升级。用户提及的自定义 ReAct Agent 是否位于下游 NL2SQL 项目或其他分支，仍需确认。

## 2. 当前实现

### 2.1 已有依赖

当前 `uv.lock` 锁定版本如下，不代表实际运行环境的安装版本：

| 组件 | 锁定版本 | 用途 |
|---|---|---|
| `langchain-core` | 1.2.5 | 消息类型、模型基础接口 |
| `langchain-community` | 0.4.1 | 使用 `ChatTongyi` 接入通义千问 |
| `langchain-openai` | 1.1.6 | 使用 `ChatOpenAI` 接入 DeepSeek 兼容接口 |
| `langgraph` | 未引入 | — |
| `deepagents` | 未引入 | — |

依赖声明见 [pyproject.toml](../../pyproject.toml)，锁定版本见 [uv.lock](../../uv.lock)。

### 2.2 模型调用方式

模型调用主要集中在 [llm_service.py](../../metaweave/services/llm_service.py)：

```text
业务代码构造提示词
    → model.invoke / ainvoke
    → 获取响应文本
    → 解析 JSON
    → 业务校验与结果保存
```

任务顺序、并发和重试由 Python 代码控制，没有发现“模型自主选择工具、观察结果、继续行动”的 ReAct 执行循环。

模块级模型覆盖由 [llm_config_resolver.py](../../metaweave/services/llm_config_resolver.py) 负责，支持业务域生成、SQL RAG、关系发现、JSON LLM 和注释生成五个模块。

## 3. 升级可行性

升级可行。2026-09-10 讨论时查询官方 PyPI 页面，最新非预发布版本为：

| 包 | 查询到的版本 | 来源 |
|---|---|---|
| `langchain` | 1.4.0 | [PyPI](https://pypi.org/project/langchain/) |
| `langgraph` | 1.2.11 | [PyPI](https://pypi.org/project/langgraph/) |
| `deepagents` | 0.7.13 | [PyPI](https://pypi.org/project/deepagents/) |

以上是讨论时的版本快照，不是已验证的依赖组合。`langchain`、`langchain-core` 和模型接入包独立发布，版本号不需要一致。实施时应重新核对版本，解析兼容依赖并更新锁文件；无需为了升级而安装所有组件。

当前模型调用集中封装，升级影响相对集中。重点验证：

- 千问和 DeepSeek 的初始化、参数透传与模型接入兼容性。
- 同步与异步调用、超时、SDK 重试和应用层重试。
- 响应内容类型是否符合现有文本解析假设。
- 五个模块的 LLM 配置覆盖行为。
- 生成产物结构兼容性及业务质量是否退化。

## 4. Deep Agents 的适用性

### 4.1 当前主流程不建议整体引入

Deep Agents 提供规划、文件操作、子 Agent 和上下文管理等能力，适合执行步骤需要动态决定的长流程。参见 [Deep Agents 官方说明](https://docs.langchain.com/oss/python/deepagents/overview)。

MetaWeave 当前主要是步骤明确的处理流程：

```text
提取表结构 → 采样 → 生成画像 → 发现关系 → 校验 → 输出
```

由明确的程序流程控制这些步骤，更便于管理执行范围、成本和可重复性。将控制权交给 Agent，不会自然提高关系判断准确率。

### 4.2 适合未来独立新增的场景

例如“交互式元数据调查”：用户指定两张表，由 Agent 自主查看字段、选择采样方式、调用验证工具，最终提交证据和结论。

此类功能可单独评估 Deep Agents，不必改变现有批量生成主流程。

如果其他项目确有自定义 ReAct Agent，应先评估标准的 `langchain.agents.create_agent` 是否足够。官方迁移指南推荐它替代旧的 `langgraph.prebuilt.create_react_agent`。是否进一步使用 Deep Agents，取决于是否需要规划、文件系统和子 Agent 等能力。参见 [LangChain v1 迁移指南](https://docs.langchain.com/oss/python/migrate/langchain-v1)。

## 5. Middleware 的适用边界

LangChain Agent Middleware 围绕 Agent 执行循环工作。当前直接调用 `model.invoke()` 的路径，不会自动经过 Agent Middleware。参见 [Middleware 官方文档](https://docs.langchain.com/oss/python/langchain/middleware/overview)。

| 当前机制 | 建议 |
|---|---|
| 模型超时、网络重试 | 在模型客户端或统一调用层整理，无需为此引入 Agent |
| 批量并发、进度回调 | 保留统一执行控制，避免分散到业务模块 |
| JSON 清理和解析 | 优先评估结构化输出 |
| 模型调用日志、耗时、Token 用量 | 在统一调用层或 callbacks 中记录 |
| 模块级模型配置覆盖 | 保留现有配置解析器 |
| 关系评分、类型兼容、SQL 校验 | 保留独立业务逻辑 |
| 未来 Agent 的工具重试、调用次数限制、动态模型选择 | 适合使用 Middleware |

Middleware 有价值，但当前项目最值得改造的机制未必需要通过它实现。

## 6. 优先采用的改进

### 6.1 结构化输出

业务域生成、JSON 增强和 SQL 样例生成等模块存在清理 Markdown 代码块、提取 JSON 和解析文本的逻辑。建议逐步评估：

```text
提示词 → 模型结构化输出 → Schema 校验 → 业务校验
```

LangChain 模型接口提供 `with_structured_output()` 等能力，可减少手工格式解析。具体实现方式取决于模型和接入适配器，需要分别验证千问与 DeepSeek，并为不支持的组合保留明确的解析回退策略。参见 [模型官方文档](https://docs.langchain.com/oss/python/langchain/models)。

结构化输出改善的是格式可靠性。字段是否存在、关系是否成立、SQL 是否符合业务意图等校验仍须保留。

相关模块：

- [domain_generator.py](../../metaweave/core/metadata/domain_generator.py)
- [json_llm_enhancer.py](../../metaweave/core/metadata/json_llm_enhancer.py)
- [sql_rag/generator.py](../../metaweave/core/sql_rag/generator.py)

### 6.2 统一调用结果与错误处理

当前异步批量调用最终失败时返回空字符串，调用方不易区分网络失败、空响应和解析失败。

建议统一记录或返回以下信息：

- 成功状态与结果。
- 错误类型和错误信息。
- 重试次数、调用耗时。
- 模型返回的 Token 用量；未提供时保留缺失状态。

同时明确 SDK 重试与应用层重试各自负责的错误范围，避免重复重试放大调用次数。调整返回接口时应同步适配调用方，或保留兼容入口。

这项改造也能为后续 REST API 作业状态和错误报告提供可靠信息。

### 6.3 按断点恢复需求决定是否引入 LangGraph

如果需要长作业失败后从已完成阶段继续执行，可以考虑 LangGraph 的状态和 checkpoint 能力。参见 [持久化官方文档](https://docs.langchain.com/oss/python/langgraph/persistence)。

引入前需明确：

- 恢复粒度是阶段、表还是批次。
- 文件输出与数据库写入如何保证幂等。
- 恢复时如何处理已发生的外部调用，避免重复副作用。
- checkpoint 与作业状态的对应关系。

LangGraph 可以作为工作流执行层，但 REST API 的作业排队、worker 管理和状态查询仍需单独设计。仅实现“启动作业、查询状态”不要求引入 LangGraph。

## 7. 建议的实施顺序与验证

1. **升级现有依赖**：解析兼容版本，更新锁文件，验证模型接入和配置覆盖。
2. **整理统一调用层**：保留 `LLMService` 入口，规范响应、错误、重试和调用指标。
3. **逐步引入结构化输出**：先选择一个 JSON 类任务验证，再扩展到其他模块。
4. **评估 LangGraph**：结合后续作业管理需求，确定是否需要持久化工作流和恢复能力。
5. **按独立需求引入 Agent**：Deep Agents 暂不进入主流程；Middleware 用于确实采用 Agent 的模块。

验证应覆盖现有模型服务、配置解析、JSON 增强、关系发现和 SQL RAG 相关测试；使用固定输入和响应样例检查解析与兼容性，再用小规模真实模型调用评估产物质量、失败率、耗时及调用成本。真实模型输出不要求逐字一致，应以结构和业务约束作为比较依据。

实施时在 WSL/Linux 使用 `.venv-wsl` 环境。当前文档仅记录静态代码检查与官方资料核对结果，尚未进行依赖安装、升级测试或模型调用验证。

## 8. 待确认事项

用户提到的自定义 ReAct Agent 位于哪个仓库或分支？如果属于下游 NL2SQL 系统，需要单独检查其工具调用、状态管理和错误恢复逻辑，才能判断采用 `create_agent` 或 Deep Agents 的迁移价值。
