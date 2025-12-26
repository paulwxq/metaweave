import asyncio


def _make_service_without_init(retry_times: int, retry_delay: float, async_concurrency: int = 1):
    from metaweave.services.llm_service import LLMService

    service = object.__new__(LLMService)
    service.use_async = True
    service.async_concurrency = async_concurrency
    service.retry_times = retry_times
    service.retry_delay = retry_delay
    return service


def test_batch_call_llm_async_retries_then_succeeds(monkeypatch):
    service = _make_service_without_init(retry_times=2, retry_delay=2)

    call_count = {"p1": 0}

    async def fake_call_llm_async(prompt: str, system_message=None):
        call_count[prompt] += 1
        if call_count[prompt] <= 2:
            raise RuntimeError("connection reset")
        return f"ok:{prompt}"

    sleep_calls = []

    async def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    import metaweave.services.llm_service as llm_service_module

    monkeypatch.setattr(service, "_call_llm_async", fake_call_llm_async)
    monkeypatch.setattr(llm_service_module.asyncio, "sleep", fake_sleep)

    results = asyncio.run(service.batch_call_llm_async(["p1"]))
    assert results == [(0, "ok:p1")]
    assert call_count["p1"] == 3  # 1 次调用 + 2 次重试
    assert sleep_calls == [2, 2]


def test_batch_call_llm_async_retries_then_gives_empty(monkeypatch):
    service = _make_service_without_init(retry_times=2, retry_delay=2)

    call_count = {"p1": 0}

    async def fake_call_llm_async(prompt: str, system_message=None):
        call_count[prompt] += 1
        raise RuntimeError("always fails")

    sleep_calls = []

    async def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    import metaweave.services.llm_service as llm_service_module

    monkeypatch.setattr(service, "_call_llm_async", fake_call_llm_async)
    monkeypatch.setattr(llm_service_module.asyncio, "sleep", fake_sleep)

    results = asyncio.run(service.batch_call_llm_async(["p1"]))
    assert results == [(0, "")]
    assert call_count["p1"] == 3  # 1 次调用 + 2 次重试
    assert sleep_calls == [2, 2]

