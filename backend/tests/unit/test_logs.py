import io
import json
import logging
from collections.abc import Iterator

import pytest

from jugrid import logs


@pytest.fixture
def captured() -> Iterator[io.StringIO]:
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    stream = io.StringIO()
    logs.configure("json", stream=stream)
    yield stream
    root.handlers, root.level = saved[0], saved[1]


def lines(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


class TestJsonLogs:
    def test_one_object_per_line_with_time_level_logger_and_message(
        self, captured: io.StringIO
    ) -> None:
        logging.getLogger("jugrid.test").info("hello %s", "world")
        [line] = lines(captured)
        assert line["message"] == "hello world"
        assert line["level"] == "INFO"
        assert line["logger"] == "jugrid.test"
        assert str(line["time"]).endswith("Z")

    def test_fields_passed_as_extra_are_top_level(self, captured: io.StringIO) -> None:
        logging.getLogger("jugrid.test").info("request", extra={"fields": {"status": 200}})
        assert lines(captured)[0]["status"] == 200

    def test_the_request_id_is_on_every_line_logged_while_it_is_set(
        self, captured: io.StringIO
    ) -> None:
        token = logs.request_id.set("abc-123")
        try:
            logging.getLogger("jugrid.test").warning("inside")
        finally:
            logs.request_id.reset(token)
        logging.getLogger("jugrid.test").warning("outside")
        inside, outside = lines(captured)
        assert inside["request_id"] == "abc-123"
        assert "request_id" not in outside

    def test_an_exception_keeps_its_traceback(self, captured: io.StringIO) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            logging.getLogger("jugrid.test").exception("failed")
        line = lines(captured)[0]
        assert "ValueError: boom" in str(line["error"])

    def test_a_field_cannot_overwrite_the_message(self, captured: io.StringIO) -> None:
        logging.getLogger("jugrid.test").info("real", extra={"fields": {"message": "fake"}})
        assert lines(captured)[0]["message"] == "real"


def test_text_logs_stay_readable() -> None:
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    stream = io.StringIO()
    try:
        logs.configure("text", stream=stream)
        logging.getLogger("jugrid.test").info("plain")
    finally:
        root.handlers, root.level = saved[0], saved[1]
    assert "INFO jugrid.test plain" in stream.getvalue()


@pytest.mark.parametrize(
    ("given", "kept"),
    [("abc-123_DEF", True), ("", False), ("x" * 65, False), ("a b", False), ("é", False)],
)
def test_only_a_short_plain_request_id_is_taken_from_the_client(given: str, kept: bool) -> None:
    assert (logs.request_id_from(given) == given) is kept
    assert 1 <= len(logs.request_id_from(given)) <= 64
