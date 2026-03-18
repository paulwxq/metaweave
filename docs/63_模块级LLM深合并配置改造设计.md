# 63_模块级LLM深合并配置改造设计

## 1. 文档目标

本文档基于当前 MetaWeave 代码现状，设计一套统一的“模块级 LLM 配置覆盖”机制，解决以下问题：

1. 当前仅 `domain_generation.llm` 做了局部覆盖，但实现为浅合并，且键语义与 `LLMService` 实际消费结构不一致。
2. 后续会有多个模块需要单独指定模型、Provider、超时、重试、LangChain 参数等，若继续各自手写合并逻辑，维护成本会快速上升。
3. 现有配置中已经出现 `model_name` 这类“文档层看似合理、代码层实际不生效”的情况，需要统一规范并收敛实现。

本文档目标不是立即改完所有模块，而是先定义统一方案、明确第一批改造范围，并给出后续可持续扩展的接入方式。

---

## 2. 当前现状

## 2.1 全局 `llm` 是当前唯一正式配置源

当前 `LLMService` 只消费完整的全局 `llm` 结构，关键字段为：

1. `active`
2. `providers`
3. `batch_size`
4. `retry_times`
5. `retry_delay`
6. `langchain_config`

`LLMService` 的实际读取逻辑是：

1. 通过 `config.get("active", "qwen")` 确定当前 provider
2. 从 `config.get("providers", {})` 中取出该 provider 的配置
3. 从 `providers[active].model` 中读取模型名

这说明 `LLMService` 需要的是“完整的标准结构 LLM 配置”，而不是某个模块自定义的一小段松散字段。

---

## 2.2 当前正式代码中的 LLM 消费点

当前仓库中主要的 LLM 消费点如下：

1. `metaweave/core/metadata/domain_generator.py`
2. `metaweave/core/metadata/generator.py`
3. `metaweave/core/metadata/json_llm_enhancer.py`
4. `metaweave/core/relationships/llm_relationship_discovery.py`
5. `metaweave/cli/sql_rag_cli.py`
6. `metaweave/cli/pipeline_cli.py`

其中只有 `DomainGenerator` 对局部配置做了特殊处理；其余模块基本都是直接取 `config["llm"]` 或 `main_config["llm"]`。

---

## 2.3 当前 `domain_generation.llm` 只实现了浅合并

当前 `DomainGenerator` 中的逻辑为：

```python
dedicated_llm = domain_gen_config.get("llm")
if dedicated_llm and isinstance(dedicated_llm, dict) and dedicated_llm:
    llm_config = {**config.get("llm", {}), **dedicated_llm}
else:
    llm_config = config.get("llm", {})
```

这段逻辑有三个特征：

1. 只在 `DomainGenerator` 内部存在，未抽象成公共能力。
2. 采用第一层字典展开，属于典型浅合并。
3. 对 `providers`、`langchain_config` 这类嵌套字典不会递归 merge，而是整块覆盖。

因此当前不支持如下直觉写法：

```yaml
domain_generation:
  llm:
    providers:
      qwen:
        model: qwen-max
```

因为这会把整个 `providers` 顶层替换掉，而不是只覆盖 `providers.qwen.model`。

---

## 2.4 当前 `model_name` 与 `provider` 等字段并不是正式语义

当前正式 `LLMService` 不识别：

1. `model_name`
2. `provider`

它识别的是：

1. `active`
2. `providers.<active>.model`

但测试和文档里已经出现了 `model_name`、`provider` 这种写法，说明仓库已经存在“文档语义”和“运行时语义”不一致的问题。

如果后续继续让多个模块各自扩展 `xxx.llm`，这种不一致会继续扩散。

---

## 2.5 当前问题总结

当前问题可以归纳为五类：

1. 模块级 LLM 覆盖能力没有统一实现。
2. 当前仅有的实现是浅合并，无法安全覆盖嵌套配置。
3. 局部配置键语义不统一，存在 `model_name`、`provider` 等非正式字段。
4. 新模块若继续复制粘贴合并逻辑，会造成配置语义分叉。
5. 现有测试里已经夹杂“按测试辅助逻辑理解的语义”，与正式代码并不完全一致。

---

## 3. 改造目标

本次改造目标如下：

1. 建立统一的“模块级 LLM 配置解析器”。
2. 对模块级 `xxx.llm` 配置实现深合并，而不是浅合并。
3. 保留顶层 `llm` 作为全局默认配置。
4. 允许多个模块各自覆盖自己的 LLM 配置。
5. 不考虑向下兼容，发现旧字段立即报错，强制配置语义收敛。
6. 尽量不改动 `LLMService` 的核心消费模型，让它继续只接收“校验并合并后的完整 llm_config”。

---

## 4. 非目标

本次改造不包含以下事项：

1. 不在 `ConfigLoader` 层面对整个 YAML 树做通用 deep merge。
2. 不将所有模块一次性全部改完，可分阶段接入。
3. 不重构 `LLMService` 的 Provider 初始化逻辑。
4. 不引入新的配置文件，继续在 `configs/metadata_config.yaml` 内完成收敛。

之所以不在 `ConfigLoader` 做全局 deep merge，是因为当前问题不是“多个 YAML 文件之间的继承”，而是“同一份大配置中，不同模块要对全局 `llm` 做局部覆盖”。把逻辑放在 LLM 配置解析层，边界更清晰、风险更小。

---

## 5. 设计原则

## 5.1 顶层 `llm` 是唯一全局默认值

顶层 `llm` 继续作为全局默认配置，含义不变：

1. 所有未显式声明局部覆盖的模块，默认使用顶层 `llm`
2. 模块级 `xxx.llm` 只是对顶层 `llm` 的覆盖补丁

---

## 5.2 模块级 `xxx.llm` 统一采用“覆盖补丁”语义

约定所有模块级 LLM 配置都满足同一语义：

> `xxx.llm` 不是一份独立完整配置，而是相对于顶层 `llm` 的覆盖补丁；运行时先取全局 `llm`，再对该补丁做结构合法性校验并执行深合并，产出最终可供 `LLMService` 消费的完整配置。

---

## 5.3 深合并只作用于 LLM 配置，不扩散到整个配置体系

即：

1. `metadata_config.yaml` 仍然由 `ConfigLoader` 直接加载
2. `ConfigLoader` 仍只负责 YAML 读取和环境变量替换
3. 只有在模块准备初始化 `LLMService` 时，才调用统一解析器构造最终 `llm_config`

---

## 5.4 不做向下兼容，只保留标准写法

本次改造明确不考虑向下兼容。

标准写法必须与 `LLMService` 的消费结构保持一致：

1. Provider 选择统一使用 `active`
2. 模型名统一使用 `providers.<provider>.model`
3. Provider 级参数统一写在 `providers.<provider>` 下
4. 全局级参数统一保留在 `llm` 顶层

以下写法一律视为非法旧配置：

1. `provider`
2. `model_name`
3. provider 级扁平字段直接写在模块级 `xxx.llm` 顶层
4. 将某模块的 LLM 参数散落到 `xxx.generation`、`xxx.validation` 等非 `xxx.llm` 路径下

发现上述字段时，运行时应直接 `raise ValueError`，而不是自动迁移、回退或 warning。

---

## 6. 目标配置模型

## 6.1 全局配置保持不变

```yaml
llm:
  active: qwen
  batch_size: 10
  retry_times: 2
  retry_delay: 2
  langchain_config:
    use_async: true
    async_concurrency: 10
    max_retries: 3
    batch_size: 50
  providers:
    qwen:
      model: qwen-plus
      api_key: ${DASHSCOPE_API_KEY}
      api_base: ${DASHSCOPE_BASE_URI}
      temperature: 0.3
      timeout: 60
      extra_params:
        enable_thinking: false
        streaming: false
    deepseek:
      model: deepseek-chat
      api_key: ${DEEPSEEK_API_KEY}
      api_base: ${DEEPSEEK_BASE_URI}
      temperature: 0.3
      timeout: 60
```

---

## 6.2 模块级配置统一使用 `xxx.llm`

本次改造规划支持的模块级路径如下：

1. `domain_generation.llm`
2. `sql_rag.llm`
3. `relationships.llm`
4. `json_llm.llm`
5. `comment_generation.llm`

说明：

1. `relationships.llm` 仅对 `rel_llm` 相关链路生效，不影响纯规则版 `rel`
2. `json_llm.llm` 仅对 `json_llm` 增强链路生效
3. `comment_generation.llm` 仅对注释生成链路生效
4. 注释生成模块的顶层配置段统一命名为 `comment_generation`，不再使用 `llm_comment_generation.llm` 这种双层 `llm` 结构

---

## 6.3 推荐的标准写法

### 示例 1：Domain Generation 切到 DeepSeek

```yaml
domain_generation:
  md_context_limit: 100
  llm:
    active: deepseek
```

### 示例 2：SQL RAG 使用更强的 Qwen 模型

```yaml
sql_rag:
  llm:
    providers:
      qwen:
        model: qwen-max
```

### 示例 3：SQL RAG 改用 DeepSeek

```yaml
sql_rag:
  llm:
    active: deepseek
```

说明：

1. 若模块级 `sql_rag.llm` 不写 `active`，则继承全局 `llm.active`
2. 若模块级 `sql_rag.llm` 写了 `active`，则覆盖全局 `llm.active`
3. 这正是“深合并下的覆盖或继承”规则

### 示例 4：SQL RAG 改用 DeepSeek 并覆盖超时

```yaml
sql_rag:
  llm:
    active: deepseek
    providers:
      deepseek:
        timeout: 120
```

### 示例 5：关系发现单独调小并发

```yaml
relationships:
  llm:
    langchain_config:
      use_async: true
      async_concurrency: 4
```

### 示例 6：注释生成单独调超时

```yaml
comment_generation:
  llm:
    providers:
      qwen:
        timeout: 120
```

---

## 6.4 SQL RAG 存量字段 `llm_timeout` 的处理原则

**实施前注意**：在正式实施第二阶段前，应先确认 `sql_rag.generation.llm_timeout` 字段是否真实存在于当前 `configs/metadata_config.yaml` 中。若该字段已不存在，则此处描述仅作历史背景参考，无需在 `_validate_nonstandard_llm_paths` 中为其增加专项检测逻辑（但 `sql_rag.generation.llm` 这类非标准路径的检测仍需保留）。

当前 `metadata_config.yaml` 中（历史上）存在：

```yaml
sql_rag:
  generation:
    llm_timeout: 120
```

该字段虽然名义上属于 SQL RAG 的 LLM 参数，但路径却位于 `sql_rag.generation` 下，和目标结构 `sql_rag.llm` 冲突；更重要的是，当前正式代码并未消费该字段。

本次改造对此字段的处理原则明确如下：

1. `sql_rag.generation.llm_timeout` 直接废弃并删除
2. 不做兼容映射
3. 不做自动迁移
4. 不做 fallback
5. 若检测到该字段，直接 `raise ValueError`

目标写法必须统一收敛为：

```yaml
sql_rag:
  llm:
    providers:
      qwen:
        timeout: 120
```

这也意味着：

1. `sql_rag.generation` 只保留业务生成参数
2. `sql_rag.llm` 统一承载 SQL RAG 的所有 LLM 参数

---

## 7. 深合并规则设计

## 7.1 总体规则

对模块级 `override_llm` 的处理顺序为：

1. 读取顶层 `llm`，得到 `base_llm`
2. 读取模块级 `xxx.llm`，得到 `override_llm`
3. 如调用方有执行期约束，再额外提供 `runtime_override`
4. 分别校验 `override_llm` 与 `runtime_override` 是否只包含标准结构允许的字段
5. 按顺序执行深合并：`base_llm <- override_llm <- runtime_override`
6. 对合并后的结果做校验
7. 将最终结果传给 `LLMService`

其中：

1. `base_llm` 表示全局默认配置
2. `override_llm` 表示模块级覆盖补丁
3. `runtime_override` 表示调用方在当前执行上下文里的临时覆盖补丁
4. 最终优先级固定为：全局默认 < 模块级覆盖 < 运行时覆盖

---

## 7.2 深合并规则细节

建议采用如下递归规则：

1. 当 base 和 override 都是 `dict` 时：
   - 对同名 key 递归合并
   - 新 key 直接追加
2. 当 override 不是 `dict` 时：
   - override 覆盖 base
3. `list` 类型默认整块覆盖，不做按位置 merge

这样可以满足当前 LLM 配置结构：

1. `providers` 是 dict，适合递归合并
2. `langchain_config` 是 dict，适合递归合并
3. `extra_params` 是 dict，适合递归合并
4. 若未来出现 list 型参数，整块覆盖更安全、可预测

---

## 7.3 示例：`providers` 深合并

给定：

```yaml
llm:
  active: qwen
  providers:
    qwen:
      model: qwen-plus
      api_key: xxx
      timeout: 60
      extra_params:
        enable_thinking: false
        streaming: false

sql_rag:
  llm:
    providers:
      qwen:
        model: qwen-max
        extra_params:
          enable_thinking: true
```

深合并后的结果应为：

```yaml
llm:
  active: qwen
  providers:
    qwen:
      model: qwen-max
      api_key: xxx
      timeout: 60
      extra_params:
        enable_thinking: true
        streaming: false
```

这正是浅合并做不到、而当前配置最需要的行为。

---

## 7.4 示例：切换 active Provider

给定：

```yaml
llm:
  active: qwen
  providers:
    qwen:
      model: qwen-plus
    deepseek:
      model: deepseek-chat

domain_generation:
  llm:
    active: deepseek
```

最终结果应为：

```yaml
active: deepseek
providers:
  qwen:
    model: qwen-plus
  deepseek:
    model: deepseek-chat
```

也就是说：

1. `active` 覆盖成功
2. `providers` 保留全量，不丢失其他 provider 配置

进一步说明：

1. 模块级配置不写 `active` 时，表示继承全局 `active`
2. 模块级配置写了 `active` 时，表示覆盖全局 `active`
3. 在深合并语义下，所有字段最终只有两种结果：覆盖或继承

---

## 8. 统一解析器设计

## 8.1 新增公共模块

建议新增：

`metaweave/services/llm_config_resolver.py`

职责：

1. 统一读取全局 `llm`
2. 读取某个模块的局部 `xxx.llm`
3. 接收调用方传入的运行时覆盖补丁
4. 校验局部补丁是否合法
5. 做深合并
6. 做最终校验

放在 `services/` 而不是 `utils/` 的原因：

1. 本次 `deep_merge_dict` 的语义是为 LLM 配置解析服务的，不是项目级通用 merge 规范
2. 它当前绑定了本设计中的覆盖规则，例如 dict 递归合并、list 整块覆盖、标量直接覆盖
3. 过早抽到 `utils/` 会让其他模块误以为这套 merge 规则可以无差别复用
4. 若未来确实出现第二个非 LLM 场景也需要同一套语义，再考虑抽到 `metaweave/utils/config_merge.py`

---

## 8.2 建议提供的 API

建议提供以下函数：

```python
def deep_merge_dict(base: dict, override: dict) -> dict:
    ...

def _validate_declared_module_llm_paths(
    full_config: dict,
    supported_paths: set[str],
) -> None:
    ...

def _validate_nonstandard_llm_paths(full_config: dict) -> None:
    ...

def _validate_override_llm_dict(override: dict, path: str) -> None:
    ...

def _validate_final_llm_config(llm_config: dict) -> None:
    ...

def resolve_module_llm_config(
    full_config: dict,
    override_path: str | None = None,
    override_dict: dict | None = None,
    runtime_override: dict | None = None,
) -> dict:
    ...
```

说明：

1. `deep_merge_dict` 只做纯递归合并，建议先作为 `llm_config_resolver.py` 内部 helper 实现，不提前抽成项目级通用工具
2. `_validate_declared_module_llm_paths(...)` 用于对白名单做全局预检，负责基于已知模块根节点列表探测整份配置中已经声明的标准 `xxx.llm` 路径
3. `_validate_nonstandard_llm_paths(...)` 用于检查 `sql_rag.generation.llm`、`relationships.rel_llm.llm` 这类声明在错误位置上的 `llm` 子树
4. `_validate_override_llm_dict` 用于校验模块级补丁和运行时补丁，只负责结构合法性与非法字段检查，不做合并
5. `_validate_final_llm_config` 用于校验深合并之后的最终 `llm_config`
6. `resolve_module_llm_config` 是模块侧唯一应该调用的入口；它内部负责串联“读取 -> override 校验 -> 深合并 -> 最终校验”
7. 如有非法旧字段，`resolve_module_llm_config` 在深合并前直接抛错
8. 若提供 `runtime_override`，其优先级高于模块级 `override_llm`
9. `runtime_override` 虽然来自代码内部而非用户 YAML，但仍必须经过与 `override_llm` 相同的结构合法性校验；若包含非法字段，同样直接报错，不做静默忽略
10. `_validate_declared_module_llm_paths(...)` 与 `_validate_nonstandard_llm_paths(...)` 都不由 `resolve_module_llm_config` 在内部自动调用；它们应由 CLI / pipeline 入口在启动阶段对整份配置单独调用一次

白名单预检的触发时机：

1. 在 CLI 或 pipeline 入口完成配置加载后立即执行
2. 在任何具体 step 开始前执行
3. 预检范围是整份 YAML，而不是当前步骤会不会实际用到某个 `xxx.llm`
4. 因此只要 YAML 中声明了当前版本未接入支持的 `xxx.llm`，无论本次运行哪个 step，都应直接报错
5. 这里的“预检”优先采用固定路径探测，而不是动态遍历整棵 YAML 树查找所有可能的 `*.llm` 路径
6. 也就是说，实现上应围绕已知模块根节点列表逐一检查其下是否声明了 `llm` 子键，例如 `domain_generation.llm`、`sql_rag.llm`、`relationships.llm`、`json_llm.llm`、`comment_generation.llm`
7. 同时，对文档明确禁止的非标准路径也应做独立固定路径探测，例如 `sql_rag.generation.llm`、`relationships.rel_llm.llm`

推荐整体执行顺序：

1. 在入口处对 `full_config` 调用 `_validate_declared_module_llm_paths(...)`
2. 在入口处对 `full_config` 调用 `_validate_nonstandard_llm_paths(...)`
3. 读取 `base_llm`
4. 读取 `override_llm`
5. 对 `override_llm` 调用 `_validate_override_llm_dict(...)`
6. 对 `runtime_override` 调用 `_validate_override_llm_dict(...)`
7. 执行 `deep_merge_dict(base_llm, override_llm)`
8. 再执行 `deep_merge_dict(merged_llm, runtime_override)`
9. 对最终结果调用 `_validate_final_llm_config(...)`

补充说明：

- 步骤 1-2 发生在 CLI / pipeline 入口
- 步骤 3-9 发生在 `resolve_module_llm_config(...)` 内部

---

## 8.3 `override_path`、`override_dict` 与 `runtime_override` 的作用

`override_path` 允许模块用统一方式声明自己的局部配置位置，例如：

1. `domain_generation.llm`
2. `sql_rag.llm`
3. `relationships.llm`
4. `json_llm.llm`
5. `comment_generation.llm`

这样模块代码里只需要写：

```python
llm_config = resolve_module_llm_config(config, "domain_generation.llm")
```

而不需要自己再去：

1. `config.get("domain_generation", {})`
2. 判断空值
3. 手写 merge
4. 自己判断哪些字段该报错

`override_dict` 用于承载代码侧直接构造的模块补丁，适合那些局部覆盖并不直接来自 YAML 固定路径、而是由调用方在运行时显式拼出的场景。

关系与约束如下：

1. `override_path` 与 `override_dict` 都用于提供模块级覆盖补丁
2. 标准场景优先使用 `override_path`，因为它直接对应 YAML 中的固定配置位置
3. `override_dict` 主要用于代码内部显式传补丁的特殊场景，不应替代常规 YAML 路径约定
4. 两者不应同时传入；若同时传入，应直接报错，避免来源歧义
5. 若 `override_path` 未声明且 `override_dict` 有值，则以 `override_dict` 作为当前调用的模块补丁来源
6. 无论补丁来自 `override_path` 还是 `override_dict`，都必须经过相同的前置结构校验

`runtime_override` 用于承载调用方在当前执行场景中的临时约束，例如：

1. pipeline 链路强制关闭异步
2. 某个批处理阶段临时调低并发
3. 某个命令在当前进程内临时缩短 timeout

这类约束不应通过直接修改 `full_config["llm"]` 来实现，而应显式作为运行时补丁传给解析器。

需要强调的是：`runtime_override` 不是“调用方自己保证正确即可”的例外输入；它与模块级 `override_llm` 一样，必须先经过结构合法性校验。若代码中误传了如 `{"model_name": "xxx"}` 这类非法字段，应立即报错，而不是静默忽略。

推荐调用方式：

```python
llm_config = resolve_module_llm_config(
    config,
    "json_llm.llm",
    runtime_override={
        "langchain_config": {
            "use_async": False,
        }
    },
)
```

这样可以保证：

1. 运行时覆盖落在最终生效的 `llm_config` 上，而不是落在某个中间配置对象上
2. 不依赖字典引用是否相同
3. 不会与模块级 `json_llm.llm` 覆盖发生目标错位

---

## 8.4 建议的校验规则

建议将校验明确分成两层：

1. 前置检测：由 `_validate_override_llm_dict(...)` 在深合并前执行，用于检查 override 输入是否合法
2. 后置校验：由 `_validate_final_llm_config(...)` 在深合并后执行，用于检查最终 `llm_config` 是否完整可用

### 8.4.1 override 校验

建议在深合并前对 `override_llm` 与 `runtime_override` 执行如下校验：

1. 若存在未知顶层 override key，直接报错
2. 若存在非法旧字段，例如 `provider`、`model_name`、`llm_timeout`，直接报错
3. 若 override 结构不是标准 `llm` 子树允许的形状，直接报错

这里的“顶层”仅指 `override_llm` 或 `runtime_override` 的第一层键，也就是 `xxx.llm` 的直接子键；不会递归检查 `providers`、`langchain_config`、`extra_params` 等合法嵌套字典内部的字段名。

这一层的重点是“输入结构是否合法”，与第 11 节的非法配置检测策略是一致的；第 11 节负责把应拦截的非法输入类型列完整，本节负责说明它发生在深合并之前。

### 8.4.2 最终结果校验

在深合并完成后，对最终 `llm_config` 执行如下校验：

1. `active` 必须存在
2. `providers` 必须存在且为 dict
3. `active` 必须在 `providers` 中存在
4. `providers[active].model` 必须存在

这一层的重点是“最终结果是否可被 `LLMService` 正常消费”，不再重复承担非法旧字段拦截职责。

本项目本次改造不接受“先 warning 后继续运行”的策略，因为这会继续掩盖应该立即修正的配置问题。

---

## 9. 模块接入设计

## 9.1 第一阶段接入模块

### 1. `DomainGenerator`

当前状态：

1. 已存在局部 `domain_generation.llm`
2. 但实现是浅合并
3. 是本次改造的直接触发点

接入方式：

```python
llm_config = resolve_module_llm_config(config, "domain_generation.llm")
self.llm_service = LLMService(llm_config)
```

---

## 9.2 第二阶段接入模块

### 1. `sql_rag_cli.py`

当前状态：

1. 直接使用全局 `llm`
2. 已有文档和测试诉求，希望 `sql_rag` 可以单独选模

接入方式：

1. 在 CLI 层构造 `llm_config = resolve_module_llm_config(main_config, "sql_rag.llm")`
2. 保持 `QuestionSQLGenerator`、`SQLValidator` 等下游接口不变

### 2. `pipeline_cli.py` 中 SQL RAG 生成链路

当前状态：

1. pipeline 生成 SQL RAG 时也直接用全局 `llm`
2. 必须与 `sql_rag_cli.py` 保持一致

接入方式：

同样改为 `resolve_module_llm_config(ctx.loaded_config, "sql_rag.llm")`

---

## 9.3 第三阶段接入模块

### 1. `LLMRelationshipDiscovery`

当前状态：

1. 直接使用 `config.get("llm", {})`
2. `rel_llm` 与全局模型强绑定

接入方式：

改为：

```python
llm_config = resolve_module_llm_config(config, "relationships.llm")
self.llm_service = LLMService(llm_config)
```

### 2. `JsonLlmEnhancer`

建议新增：

```yaml
json_llm:
  llm:
    ...
```

补充说明：

1. `JsonLlmEnhancer` 自身应消费 `resolve_module_llm_config(config, “json_llm.llm”)` 的结果
2. `pipeline_cli.py` 中当前存在”强制 `langchain_config.use_async = False`”的运行时行为
3. 该行为在改造后不应继续通过直接修改 `cli_config[“llm”]` 实现
4. 应改为通过 `runtime_override={“langchain_config”: {“use_async”: False}}` 显式传入解析器
5. 接口改动方向：`JsonLlmEnhancer.__init__` 新增 `runtime_override: dict | None = None` 参数，内部将其传给 `resolve_module_llm_config`；`pipeline_cli.py` 在构造 `JsonLlmEnhancer` 时显式传入该参数，彻底移除原有直接修改 `config[“llm”]` 的逻辑

推荐写法：

```python
# pipeline_cli.py 中
enhancer = JsonLlmEnhancer(
    cli_config,
    runtime_override={
        “langchain_config”: {
            “use_async”: False,
        }
    },
)
```

```python
# json_llm_enhancer.py 中
class JsonLlmEnhancer:
    def __init__(self, config: dict, runtime_override: dict | None = None):
        llm_config = resolve_module_llm_config(
            config,
            “json_llm.llm”,
            runtime_override=runtime_override,
        )
        self.llm_service = LLMService(llm_config)
        ...
```

---

## 9.4 第四阶段接入模块

### 1. `MetadataGenerator` 的注释生成链路

建议将现有配置段重命名为：

```yaml
comment_generation:
  enabled: true
  language: zh
  llm:
    ...
```

说明：

1. 目标命名使用 `comment_generation.llm`
2. 不再继续使用 `llm_comment_generation.llm`
3. 这样可以避免顶层名称已带 `llm`、子节点再套一层 `llm` 的视觉重复
4. 这是一个明确的 breaking change，不做兼容；已有 `llm_comment_generation` 配置必须同步改为 `comment_generation`
5. 相关消费代码与测试必须在同一阶段一起修改，不能只改文档命名而不改运行时代码
6. `comment_generation.llm` 的解析器接入点明确放在 `metaweave/core/metadata/generator.py`
7. 也就是说，由 `MetadataGenerator` 在内部调用 `resolve_module_llm_config(config, "comment_generation.llm")` 构造注释生成链路专用的 `llm_config`
8. `CommentGenerator` 本身不负责解析配置，它继续只接收已经构造好的 `LLMService`
9. `json_llm_enhancer.py` 在第四阶段只需要把 `config.get("llm_comment_generation", {})` 同步改为 `config.get("comment_generation", {})` 并调整相关日志文案
10. `json_llm_enhancer.py` 不承担 `comment_generation.llm` 的解析器接入职责；该职责仍放在 `generator.py`

### 2. 其他未来 LLM 模块

只要遵守“模块下新增 `llm` 段”的约定，即可无缝复用统一解析器。

---

## 10. 与现有代码的改造边界

## 10.1 必改文件

整个改造过程中至少会涉及这些文件：

1. `metaweave/services/llm_config_resolver.py`
2. `metaweave/core/metadata/domain_generator.py`
3. `metaweave/cli/sql_rag_cli.py`
4. `metaweave/cli/pipeline_cli.py`
5. `metaweave/core/relationships/llm_relationship_discovery.py`
6. `metaweave/core/metadata/generator.py`
7. `metaweave/core/metadata/json_llm_enhancer.py`
8. `configs/metadata_config.yaml`

---

## 10.2 建议同步调整的测试文件

1. `tests/unit/metaweave/metadata/test_domain_mapping_refactor.py`
2. 新增 `tests/unit/metaweave/services/test_llm_config_resolver.py`
3. `tests/test_sql_rag_training_scenario.py`
4. `tests/unit/test_step_all_orchestrator.py`

其中：

1. `test_domain_mapping_refactor.py` 当前测试里还在使用旧语义（使用了 `provider`、`model_name` 等非法字段），且其测试逻辑本身是在验证旧的浅合并行为；改造后**不能只做字段替换**，必须完整重写测试逻辑，改为验证：深合并正确性（`providers` 层级递归合并）、非法字段触发 `ValueError`、`active` 切换生效等新行为
2. `test_sql_rag_training_scenario.py` 当前手动读取旧字段，与正式代码目标结构不一致
3. `test_step_all_orchestrator.py` 当前仍直接使用 `llm_comment_generation`

这些测试应直接改成标准写法，不保留旧字段测试。

---

## 10.3 不建议修改的文件

本次改造不建议改动：

1. `services/config_loader.py`
2. `metaweave/services/llm_service.py` 的核心初始化流程

理由：

1. `ConfigLoader` 不应承担模块级语义 merge 逻辑
2. `LLMService` 当前消费“标准完整 llm_config”的模型是稳定的，改它只会扩大风险面

---

## 11. 前置非法配置检测策略

本次改造明确采用严格策略：旧字段、错层级字段、非标准写法全部直接报错。

本节描述的是“深合并前的前置检测”范围，对应 `_validate_declared_module_llm_paths(...)`、`_validate_nonstandard_llm_paths(...)` 与 `_validate_override_llm_dict(...)`；不与 8.4.2 的最终结果校验混用。

建议解析器至少检测以下非法配置：

1. `domain_generation.llm.provider`
2. `domain_generation.llm.model_name`
3. `sql_rag.generation.llm_timeout`
4. 模块级 `xxx.llm` 顶层出现 `temperature`、`timeout`、`api_key`、`api_base`、`max_tokens`、`extra_params`
5. 使用 `sql_rag.generation.llm`、`relationships.rel_llm.llm` 等非标准路径
6. 在当前版本尚未接入支持白名单的模块上，提前声明对应的 `xxx.llm`

其中第 4 条仅针对 `xxx.llm` 的第一层键生效，不递归检查 `providers.<provider>`、`langchain_config`、`extra_params` 等合法嵌套结构内部的字段名；例如 `providers.qwen.timeout`、`providers.qwen.temperature`、`providers.qwen.extra_params` 都属于标准合法写法。

报错原则：

1. 错误信息要直接指出非法字段全路径
2. 错误信息要给出目标标准写法
3. 不做自动修正
4. 不继续运行

建议同时维护一份显式白名单，例如：

```python
SUPPORTED_MODULE_LLM_PATHS = {
    "domain_generation.llm",
    "sql_rag.llm",
}
```

规则如下：

1. 只有已接入模块，才允许在 YAML 中出现对应的 `xxx.llm`
2. 未接入模块若提前声明 `xxx.llm`，运行时直接报错，不允许 silent ignore
3. 每推进一个实施阶段，都同步扩展该白名单
4. 白名单应与 README、`metadata_config.yaml` 注释、测试用例保持一致

白名单与非标准路径预检的触发方式明确如下：

1. 该校验不是等某个模块调用 `resolve_module_llm_config(...)` 时才触发
2. 而是在 CLI / pipeline 入口加载完配置后，对整份 YAML 执行一次全局预检
3. `_validate_declared_module_llm_paths(...)` 应基于已知模块根节点列表做固定路径探测，检查所有可能声明的标准模块级 `xxx.llm` 路径
4. `_validate_nonstandard_llm_paths(...)` 应基于固定禁止路径列表探测 `sql_rag.generation.llm`、`relationships.rel_llm.llm` 这类非标准路径
5. 若发现标准路径不在 `SUPPORTED_MODULE_LLM_PATHS` 中，立即报错
6. 若发现非标准路径被声明，立即报错
7. 因此即使本次命令不会实际走到对应 step，也不能在配置里提前声明未接入模块的 `xxx.llm`，也不能把 `llm` 写到错误层级

---

## 12. 风险与注意事项

## 12.1 风险 1：多个模块各自定义了不同的局部 LLM 路径

如果不统一路径规范，未来可能出现：

1. `sql_rag.llm`
2. `sql_rag.generation.llm`
3. `rel_llm.llm`
4. `relationships.llm`

混用会导致长期维护困难。

建议本次文档即明确约定：

1. 优先用“模块根节点下的 `llm`”
2. 不建议把 `llm` 下沉到更深层，除非确有必要

---

## 12.2 风险 2：历史配置和历史测试会一次性暴露问题

由于本次改造不做兼容，原先依赖旧字段或错误层级的配置、文档、测试会集中失败。

这不是缺点，而是预期行为；它能尽快暴露并清理仓库中的错误语义。

建议：

1. 接入某模块时，同步清理该模块相关配置样例
2. 同步修改对应测试
3. 不保留“旧字段也能跑”的灰色状态

---

## 12.3 风险 3：某些测试依赖旧行为

目前已有测试文件内含旧语义和测试辅助逻辑，尤其是：

1. `tests/unit/metaweave/metadata/test_domain_mapping_refactor.py`
2. `tests/test_sql_rag_training_scenario.py`

如果只改生产代码、不改测试，测试可能出现：

1. 语义偏差
2. 断言对象不再代表真实运行行为

因此建议把“测试对齐”视为本次改造的一部分，而不是后置事项。

---

## 12.4 风险 4：分阶段实施期间出现“配置已写但暂未生效”的误解

本方案允许分阶段接入模块，这意味着阶段之间会存在短暂的能力不对称。

例如：

1. 第一阶段只接入 `domain_generation.llm`
2. 若此时用户提前在 YAML 中写入 `sql_rag.llm`
3. 而 `sql_rag_cli.py` 尚未接入统一解析器
4. 就会出现“配置写了，但链路还未支持”的风险窗口

为避免这种中间状态造成困惑，本次方案要求同时采取两层措施：

1. 文档层：
   - 在 README 中标明“当前已支持模块级 LLM 覆盖”的模块清单
   - 在 `configs/metadata_config.yaml` 中用注释标明哪些模块已经接入
2. 运行时层：
   - 使用 `SUPPORTED_MODULE_LLM_PATHS` 白名单约束当前版本可声明的 `xxx.llm`
   - 在 CLI / pipeline 入口加载配置后，先对整份 YAML 做白名单全局预检
   - 未接入模块一旦提前声明 `xxx.llm`，立即报错

本项目不接受“先写上，暂时不生效”的灰色状态。

---

## 12.5 风险 5：`llm_comment_generation` 重命名为 `comment_generation` 的改造是显式 breaking change

该重命名不是局部文档优化，而是会影响配置、代码、测试的整体验证路径。

具体影响包括：

1. 所有现有 `metadata_config.yaml` 中的 `llm_comment_generation` 都必须改为 `comment_generation`
2. 直接读取该配置段的代码必须同步修改，例如：
   - `metaweave/core/metadata/generator.py`
   - `metaweave/core/metadata/json_llm_enhancer.py`
3. 直接引用旧节点名的测试必须同步修改，例如：
   - `tests/unit/test_step_all_orchestrator.py`
4. 若只改文档命名、不改运行时代码，会出现“设计已收敛、代码仍读旧键名”的不一致

因此该项不应作为零散小改处理，而应作为第四阶段中的独立改造任务统一落地。

---

## 13. 实施建议

## 13.0 阶段间状态管理

每个阶段完成后，除代码接入外，还应同步完成以下动作：

1. 扩展 `SUPPORTED_MODULE_LLM_PATHS` 白名单
2. 更新 README 中的“已支持模块级 LLM 覆盖”列表
3. 更新 `configs/metadata_config.yaml` 中对应模块的注释样例
4. 补齐当前阶段支持范围内的单测

只有以上动作一并完成，才算该阶段真正收口。

## 13.1 第一阶段：建立公共解析器并替换浅合并

建议顺序：

1. 新增 `metaweave/services/llm_config_resolver.py`（含 `deep_merge_dict`、`_validate_declared_module_llm_paths`、`_validate_nonstandard_llm_paths`、`_validate_override_llm_dict`、`_validate_final_llm_config`、`resolve_module_llm_config`）
2. 改造 CLI/pipeline 入口（`metaweave/cli/metadata_cli.py` 与 `metaweave/cli/pipeline_cli.py`），在加载配置后、任何 step 执行前立即调用 `_validate_declared_module_llm_paths` 与 `_validate_nonstandard_llm_paths` 对整份配置做全局预检
3. 改造 `DomainGenerator`，用 `resolve_module_llm_config(config, "domain_generation.llm")` 替换现有浅合并逻辑
4. 同步清理 `configs/metadata_config.yaml` 中 `domain_generation.llm` 下的旧字段（当前存在 `model_name: qwen-max`），改写为标准写法（`providers.qwen.model: qwen-max` 或直接删除覆盖）
5. 补 resolver 单测
6. 补 `DomainGenerator` 深合并与非法字段报错单测

说明：步骤 2 必须在步骤 3 之前或同步完成，否则验收标准第 5 条无法满足——全局预检不由 `resolve_module_llm_config` 内部自动触发，只有入口主动调用才会生效。步骤 4 必须与步骤 3 同步完成，否则改造完成后第一次运行就会因自身配置文件触发 ValueError。

验收标准：

1. `domain_generation.llm.active: deepseek` 生效
2. `domain_generation.llm.providers.qwen.model: qwen-max` 生效且不丢其他 provider 字段
3. `domain_generation.llm.model_name: qwen-max` 直接报错
4. README 与 `metadata_config.yaml` 明确标注当前只有 `domain_generation.llm` 已接入
5. 若提前声明 `sql_rag.llm`，运行时直接报错
6. 任意非法字段触发报错时，错误信息至少包含非法字段全路径与目标标准写法

---

## 13.2 第二阶段：接入 SQL RAG

建议顺序：

1. 改造 `sql_rag_cli.py`
2. 改造 `pipeline_cli.py` 中 SQL RAG 生成链路
3. 补 `sql_rag.llm` 配置样例
4. 调整相关测试

验收标准：

1. CLI 与 pipeline 两条链路行为一致
2. 不配置 `sql_rag.llm` 时完全继承全局 `llm`
3. 配置 `sql_rag.llm` 时只影响 SQL RAG，不影响其他模块
4. `sql_rag.generation.llm_timeout` 存在时直接报错
5. README、`metadata_config.yaml` 注释、白名单三者同步包含 `sql_rag.llm`
6. 任意非法字段触发报错时，错误信息至少包含非法字段全路径与目标标准写法

---

## 13.3 第三阶段：接入关系发现与 JSON 增强

建议顺序：

1. `relationships.llm`
2. `json_llm.llm`
3. `pipeline_cli.py` 中 `json_llm` 链路的运行时覆盖改造

验收标准：

1. 各模块局部覆盖互不干扰
2. 所有模块都通过同一解析器构造最终 `llm_config`
3. 仓库中不再出现新的手写 merge 逻辑
4. `pipeline_cli.py` 中 `json_llm` 链路通过 `runtime_override` 强制 `use_async: false`
5. README、`metadata_config.yaml` 注释、白名单三者同步反映新增支持模块
6. 任意非法字段触发报错时，错误信息至少包含非法字段全路径与目标标准写法

---

## 13.4 第四阶段：`llm_comment_generation` 重命名为 `comment_generation`

该阶段是独立的 breaking change 收口阶段。

建议顺序：

1. 将 `configs/metadata_config.yaml` 中的 `llm_comment_generation` 全量改为 `comment_generation`
2. 改造 `metaweave/core/metadata/generator.py` 中对 `config.get("llm_comment_generation", {})` 的读取
3. 改造 `metaweave/core/metadata/json_llm_enhancer.py` 中对 `config.get("llm_comment_generation", {})` 的读取及相关日志文案
4. 在 `metaweave/core/metadata/generator.py` 内部调用 `resolve_module_llm_config(config, "comment_generation.llm")`，为注释生成链路构造专用 `llm_config`
5. 调整直接引用旧节点名的测试和样例配置
6. 同步更新 README 与 `metadata_config.yaml` 注释

接入点说明：

1. `generator.py` 是该链路的配置读取与对象装配入口
2. 因此 `comment_generation.llm` 不采用“由外部调用方注入已解析好 `llm_config`”的方式
3. 而是由 `MetadataGenerator` 在内部直接解析后创建 `LLMService`
4. `CommentGenerator` 继续保持只接收 `LLMService`，不引入配置解析职责

验收标准：

1. 仓库主配置中不再出现 `llm_comment_generation`
2. `generator.py` 与 `json_llm_enhancer.py` 均改为读取 `comment_generation`
3. `comment_generation.llm` 可以独立覆盖全局 `llm`
4. 直接引用旧节点名的测试全部同步更新
5. 该 breaking change 不保留兼容分支
6. 若仍使用旧节点名或旧字段，运行时报错且错误信息至少包含旧字段全路径与目标标准写法

---

## 14. 预期收益

完成本次改造后，可以获得以下收益：

1. 模块级 LLM 覆盖语义统一，不再各自为政。
2. 配置真正支持深合并，`providers`、`langchain_config`、`extra_params` 可以安全覆盖。
3. `domain_generation`、`sql_rag` 等模块中的错误旧字段会被快速清理，不再被兼容逻辑掩盖。
4. 后续新增模块若需要独立 LLM，只需新增 `xxx.llm` 并接入统一解析器。
5. `LLMService` 继续保持单一职责，系统整体改动面可控。

---

## 15. 结论

基于当前代码现状，最合理的改造方向不是在每个模块里继续手写浅合并，而是：

1. 保留顶层 `llm` 作为全局默认配置
2. 为所有模块统一引入 `xxx.llm` 局部覆盖补丁语义
3. 新增公共 LLM 配置解析器，负责标准结构校验与深合并
4. 让所有模块都在初始化 `LLMService` 前调用这一解析器

这样既能解决当前 `domain_generation` 的问题，也能为后续多个模块单独配置 LLM 提供稳定、可扩展、可测试的统一基础设施。
