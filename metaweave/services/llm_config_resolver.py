"""统一的模块级 LLM 配置解析器。

职责：
1. 提供全局预检函数，在 CLI/pipeline 入口对整份配置做白名单校验
2. 对模块级 xxx.llm 补丁执行结构合法性校验
3. 对全局 llm 与模块级补丁执行深合并
4. 对最终合并结果执行完整性校验
5. 提供统一入口 resolve_module_llm_config 供各模块调用

使用方式：
    # CLI/pipeline 入口（全局预检，启动阶段调用一次）
    from metaweave.services.llm_config_resolver import (
        _validate_declared_module_llm_paths,
        _validate_nonstandard_llm_paths,
    )
    _validate_declared_module_llm_paths(full_config)
    _validate_nonstandard_llm_paths(full_config)

    # 各模块初始化 LLMService 前调用
    from metaweave.services.llm_config_resolver import resolve_module_llm_config
    llm_config = resolve_module_llm_config(config, "domain_generation.llm")
    self.llm_service = LLMService(llm_config)
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# 已支持模块级 LLM 覆盖的路径白名单
# 每推进一个实施阶段，同步扩展此白名单
# --------------------------------------------------------------------------
SUPPORTED_MODULE_LLM_PATHS: set[str] = {
    "domain_generation.llm",
}

# 所有已知可能存在 xxx.llm 子键的模块根节点
# 用于白名单预检的固定路径探测
_ALL_KNOWN_MODULE_ROOTS: set[str] = {
    "domain_generation",
    "sql_rag",
    "relationships",
    "json_llm",
    "comment_generation",
}

# 明确禁止的非标准路径（错误层级写法）
_NONSTANDARD_LLM_PATHS: list[str] = [
    "sql_rag.generation.llm",
    "relationships.rel_llm.llm",
]

# override 顶层允许的合法键（对应 LLMService 消费的 llm 结构）
_VALID_OVERRIDE_TOP_KEYS: set[str] = {
    "active",
    "providers",
    "batch_size",
    "retry_times",
    "retry_delay",
    "langchain_config",
}

# 非法旧字段（在 override 顶层出现时直接报错）
_ILLEGAL_LEGACY_KEYS: set[str] = {
    "provider",
    "model_name",
    "llm_timeout",
    "temperature",
    "timeout",
    "api_key",
    "api_base",
    "max_tokens",
    "extra_params",
}


def deep_merge_dict(base: dict, override: dict) -> dict:
    """递归合并两个字典，返回新字典（不修改原始对象）。

    合并规则：
    - base 和 override 都是 dict 时：同名 key 递归合并，新 key 直接追加
    - override 值不是 dict 时：override 覆盖 base
    - list 类型整块覆盖，不做按位置 merge
    """
    result = dict(base)
    for key, override_val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(override_val, dict):
            result[key] = deep_merge_dict(result[key], override_val)
        else:
            result[key] = override_val
    return result


def _validate_declared_module_llm_paths(full_config: dict) -> None:
    """对整份配置中已声明的标准模块级 xxx.llm 路径做白名单预检。

    遍历所有已知模块根节点，检查其下是否声明了 llm 子键；
    若声明了但不在 SUPPORTED_MODULE_LLM_PATHS 白名单中，立即报错。

    此函数应在 CLI / pipeline 入口加载完配置后立即调用，早于任何 step 执行。
    """
    for module_root in _ALL_KNOWN_MODULE_ROOTS:
        module_cfg = full_config.get(module_root)
        if not isinstance(module_cfg, dict):
            continue
        if "llm" not in module_cfg:
            continue
        path = f"{module_root}.llm"
        if path not in SUPPORTED_MODULE_LLM_PATHS:
            raise ValueError(
                f"配置错误：检测到 '{path}'，但该模块尚未支持模块级 LLM 覆盖。\n"
                f"当前已支持的模块级 LLM 路径：{sorted(SUPPORTED_MODULE_LLM_PATHS)}\n"
                f"请删除配置中的 '{path}'，或等待该模块完成改造接入后再使用。"
            )


def _validate_nonstandard_llm_paths(full_config: dict) -> None:
    """检查明确禁止的非标准 llm 路径（错误层级写法）。

    此函数应在 CLI / pipeline 入口加载完配置后立即调用，早于任何 step 执行。
    """
    for dotted_path in _NONSTANDARD_LLM_PATHS:
        parts = dotted_path.split(".")
        node = full_config
        found = True
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                found = False
                break
            node = node[part]
        if found:
            raise ValueError(
                f"配置错误：检测到非标准 LLM 路径 '{dotted_path}'。\n"
                f"LLM 参数应统一写在对应模块根节点下的 'llm' 子键中。\n"
                f"例如请将 '{dotted_path}' 相关参数移至标准路径（如 sql_rag.llm）。"
            )


def _validate_override_llm_dict(override: dict, path: str) -> None:
    """校验模块级补丁或运行时补丁的结构合法性。

    只检查 override 的顶层键：
    - 存在非法旧字段（如 provider、model_name）→ 报错并给出目标写法
    - 存在未知顶层键 → 报错

    注意：不递归检查 providers.<provider>、langchain_config、extra_params 内部字段。
    """
    for key in override:
        if key in _ILLEGAL_LEGACY_KEYS:
            raise ValueError(
                f"配置错误：在 '{path}' 中检测到非法旧字段 '{key}'。\n"
                f"标准写法：\n"
                f"  - 模型名请写在 providers.<provider>.model\n"
                f"  - provider 选择请使用 active 字段\n"
                f"  - timeout/temperature 等参数请写在 providers.<provider> 下\n"
                f"非法字段全路径：{path}.{key}"
            )
        if key not in _VALID_OVERRIDE_TOP_KEYS:
            raise ValueError(
                f"配置错误：在 '{path}' 中检测到未知顶层字段 '{key}'。\n"
                f"合法的顶层字段为：{sorted(_VALID_OVERRIDE_TOP_KEYS)}\n"
                f"非法字段全路径：{path}.{key}"
            )


def _validate_final_llm_config(llm_config: dict) -> None:
    """校验深合并后的最终 llm_config 是否可被 LLMService 正常消费。

    检查项：
    1. active 必须存在
    2. providers 必须存在且为 dict
    3. active 必须在 providers 中存在
    4. providers[active].model 必须存在
    """
    if "active" not in llm_config:
        raise ValueError(
            "LLM 配置错误：最终 llm_config 缺少 'active' 字段。\n"
            "请在全局 llm 或模块级 llm 中指定 active: <provider_name>。"
        )
    if "providers" not in llm_config or not isinstance(llm_config["providers"], dict):
        raise ValueError(
            "LLM 配置错误：最终 llm_config 缺少 'providers' 字段或格式不正确。\n"
            "请确保 llm.providers 为字典结构。"
        )
    active = llm_config["active"]
    if active not in llm_config["providers"]:
        raise ValueError(
            f"LLM 配置错误：active='{active}' 但 providers 中不存在该 provider。\n"
            f"已配置的 providers：{list(llm_config['providers'].keys())}\n"
            f"请在 llm.providers 下添加 '{active}' 的配置，或修改 active 为已有 provider。"
        )
    provider_cfg = llm_config["providers"][active]
    if not isinstance(provider_cfg, dict) or "model" not in provider_cfg:
        raise ValueError(
            f"LLM 配置错误：providers.{active}.model 必须存在。\n"
            f"请在 llm.providers.{active} 下添加 model: <model_name>。"
        )


def resolve_module_llm_config(
    full_config: dict,
    override_path: str | None = None,
    override_dict: dict | None = None,
    runtime_override: dict | None = None,
) -> dict:
    """模块侧唯一应该调用的入口。

    串联执行：读取 -> override 校验 -> 深合并 -> 最终校验

    Args:
        full_config: 完整的配置字典（即整份 metadata_config.yaml 加载结果）
        override_path: 模块级 LLM 配置的 YAML 点分路径，如 "domain_generation.llm"
        override_dict: 代码侧直接构造的模块补丁（与 override_path 不可同时传入）
        runtime_override: 运行时临时覆盖补丁，优先级高于模块级 override

    Returns:
        可直接传给 LLMService 的完整 llm_config 字典

    Raises:
        ValueError: 非法字段、路径歧义、或最终配置不完整时抛出
    """
    if override_path is not None and override_dict is not None:
        raise ValueError(
            "resolve_module_llm_config: override_path 与 override_dict 不可同时传入。\n"
            "请选择其中一种方式提供模块级补丁：\n"
            "  - override_path: 指向 YAML 中的固定路径，如 'domain_generation.llm'\n"
            "  - override_dict: 代码侧直接构造的补丁字典"
        )

    # 1. 读取全局 base_llm（深拷贝，避免污染原始配置）
    base_llm = dict(full_config.get("llm", {}))

    # 2. 读取模块级 override_llm
    override_llm: dict | None = None
    path_label: str = "<none>"

    if override_path is not None:
        path_label = override_path
        parts = override_path.split(".")
        node: object = full_config
        found = True
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                found = False
                break
            node = node[part]
        if found and isinstance(node, dict) and node:
            override_llm = node
    elif override_dict is not None:
        override_llm = override_dict
        path_label = "<override_dict>"

    # 3. 校验 override_llm 结构合法性
    if override_llm:
        _validate_override_llm_dict(override_llm, path_label)

    # 4. 校验 runtime_override 结构合法性
    if runtime_override:
        _validate_override_llm_dict(runtime_override, "<runtime_override>")

    # 5. 深合并：base_llm <- override_llm
    merged = base_llm
    if override_llm:
        merged = deep_merge_dict(merged, override_llm)

    # 6. 深合并：merged <- runtime_override
    if runtime_override:
        merged = deep_merge_dict(merged, runtime_override)

    # 7. 最终校验
    _validate_final_llm_config(merged)

    return merged
