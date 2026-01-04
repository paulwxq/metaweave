import logging

from metaweave.utils import logger as mw_logger


class _CaptureHandler(logging.Handler):
    def __init__(self, sink):
        super().__init__()
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self._sink.append(record)


def test_step_filter_allows_only_configured_steps():
    record = logging.LogRecord(
        name="metaweave.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )

    mw_logger.set_current_step("ddl")
    f = mw_logger.StepFilter(["ddl"])
    assert f.filter(record) is True

    mw_logger.set_current_step("json")
    assert f.filter(record) is False


def test_log_record_factory_injects_step():
    old_factory = logging.getLogRecordFactory()
    try:
        mw_logger._STEP_RECORD_FACTORY_INSTALLED = False
        mw_logger._install_step_log_record_factory()
        mw_logger.set_current_step("ddl")

        records = []
        handler = _CaptureHandler(records)

        logger = logging.getLogger("metaweave.test.step_factory")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        logger.propagate = False

        logger.info("hello")
        assert records, "expected at least one record"
        assert getattr(records[0], "step", None) == "ddl"
    finally:
        logging.setLogRecordFactory(old_factory)
        mw_logger._STEP_RECORD_FACTORY_INSTALLED = False
