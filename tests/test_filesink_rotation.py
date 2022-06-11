import datetime
import os
import pathlib
import tempfile
import time
from unittest.mock import Mock

import loguru
import pytest
from loguru import logger
from loguru._ctime_functions import load_ctime_functions

from .conftest import check_dir


@pytest.fixture
def tmp_path_local(reset_logger):
    # Pytest 'tmp_path' creates directories in /tmp, but /tmp does not support xattr,
    # causing some tests would fail.
    with tempfile.TemporaryDirectory(dir=".") as tmp_path:
        yield pathlib.Path(tmp_path)
        logger.remove()  # Deleting file not possible if still in use by Loguru.


def test_renaming(freeze_time, tmp_path):
    with freeze_time("2020-01-01") as frozen:
        logger.add(tmp_path / "file.log", rotation=0, format="{message}")

        frozen.tick()
        logger.debug("a")

        check_dir(
            tmp_path,
            files=[
                ("file.2020-01-01_00-00-00_000000.log", ""),
                ("file.log", "a\n"),
            ],
        )

        frozen.tick()
        logger.debug("b")

        check_dir(
            tmp_path,
            files=[
                ("file.2020-01-01_00-00-00_000000.log", ""),
                ("file.2020-01-01_00-00-01_000000.log", "a\n"),
                ("file.log", "b\n"),
            ],
        )


def test_no_renaming(freeze_time, tmp_path):
    with freeze_time("2018-01-01 00:00:00") as frozen:
        logger.add(tmp_path / "file_{time}.log", rotation=0, format="{message}")

        frozen.move_to("2019-01-01 00:00:00")
        logger.debug("a")
        check_dir(
            tmp_path,
            files=[
                ("file_2018-01-01_00-00-00_000000.log", ""),
                ("file_2019-01-01_00-00-00_000000.log", "a\n"),
            ],
        )

        frozen.move_to("2020-01-01 00:00:00")
        logger.debug("b")
        check_dir(
            tmp_path,
            files=[
                ("file_2018-01-01_00-00-00_000000.log", ""),
                ("file_2019-01-01_00-00-00_000000.log", "a\n"),
                ("file_2020-01-01_00-00-00_000000.log", "b\n"),
            ],
        )


@pytest.mark.parametrize("size", [8, 8.0, 7.99, "8 B", "8e-6MB", "0.008 kiB", "64b"])
def test_size_rotation(freeze_time, tmp_path, size):
    with freeze_time("2018-01-01 00:00:00") as frozen:
        i = logger.add(tmp_path / "test_{time}.log", format="{message}", rotation=size, mode="w")

        frozen.tick()
        logger.debug("abcde")

        frozen.tick()
        logger.debug("fghij")

        frozen.tick()
        logger.debug("klmno")

        frozen.tick()
        logger.remove(i)

    check_dir(
        tmp_path,
        files=[
            ("test_2018-01-01_00-00-00_000000.log", "abcde\n"),
            ("test_2018-01-01_00-00-02_000000.log", "fghij\n"),
            ("test_2018-01-01_00-00-03_000000.log", "klmno\n"),
        ],
    )


@pytest.mark.parametrize(
    "when, hours",
    [
        # hours = [
        #   Should not trigger, should trigger, should not trigger, should trigger, should trigger
        # ]
        ("13", [0, 1, 20, 4, 24]),
        ("13:00", [0.2, 0.9, 23, 1, 48]),
        ("13:00:00", [0.5, 1.5, 10, 15, 72]),
        ("13:00:00.123456", [0.9, 2, 10, 15, 256]),
        ("11:00", [22.9, 0.2, 23, 1, 24]),
        ("w0", [11, 1, 24 * 7 - 1, 1, 24 * 7]),
        ("W0 at 00:00", [10, 24 * 7 - 5, 0.1, 24 * 30, 24 * 14]),
        ("W6", [24, 24 * 28, 24 * 5, 24, 364 * 24]),
        ("saturday", [25, 25 * 12, 0, 25 * 12, 24 * 8]),
        ("w6 at 00", [8, 24 * 7, 24 * 6, 24, 24 * 8]),
        (" W6 at 13 ", [0.5, 1, 24 * 6, 24 * 6, 365 * 24]),
        ("w2  at  11:00:00 AM", [48 + 22, 3, 24 * 6, 24, 366 * 24]),
        ("MoNdAy at 11:00:30.123", [22, 24, 24, 24 * 7, 24 * 7]),
        ("sunday", [0.1, 24 * 7 - 10, 24, 24 * 6, 24 * 7]),
        ("SUNDAY at 11:00", [1, 24 * 7, 2, 24 * 7, 30 * 12]),
        ("sunDAY at 1:0:0.0 pm", [0.9, 0.2, 24 * 7 - 2, 3, 24 * 8]),
        (datetime.time(15), [2, 3, 19, 5, 24]),
        (datetime.time(18, 30, 11, 123), [1, 5.51, 20, 24, 40]),
        ("2 h", [1, 2, 0.9, 0.5, 10]),
        ("1 hour", [0.5, 1, 0.1, 100, 1000]),
        ("7 days", [24 * 7 - 1, 1, 48, 24 * 10, 24 * 365]),
        ("1h 30 minutes", [1.4, 0.2, 1, 2, 10]),
        ("1 w, 2D", [24 * 8, 24 * 2, 24, 24 * 9, 24 * 9]),
        ("1.5d", [30, 10, 0.9, 48, 35]),
        ("1.222 hours, 3.44s", [1.222, 0.1, 1, 1.2, 2]),
        (datetime.timedelta(hours=1), [0.9, 0.2, 0.7, 0.5, 3]),
        (datetime.timedelta(minutes=30), [0.48, 0.04, 0.07, 0.44, 0.5]),
        ("hourly", [0.9, 0.2, 0.8, 3, 1]),
        ("daily", [11, 1, 23, 1, 24]),
        ("WEEKLY", [11, 2, 24 * 6, 24, 24 * 7]),
        ("mOnthLY", [0, 24 * 13, 29 * 24, 60 * 24, 24 * 35]),
        ("monthly", [10 * 24, 30 * 24 * 6, 24, 24 * 7, 24 * 31]),
        ("Yearly ", [100, 24 * 7 * 30, 24 * 300, 24 * 100, 24 * 400]),
    ],
)
def test_time_rotation(freeze_time, tmp_path, when, hours):
    with freeze_time("2017-06-18 12:00:00") as frozen:  # Sunday
        i = logger.add(
            tmp_path / "test_{time}.log",
            format="{message}",
            rotation=when,
            mode="w",
        )

        for h, m in zip(hours, ["a", "b", "c", "d", "e"]):
            frozen.tick(delta=datetime.timedelta(hours=h))
            logger.debug(m)

        logger.remove(i)

    content = [path.read_text() for path in sorted(tmp_path.iterdir())]
    assert content == ["a\n", "b\nc\n", "d\n", "e\n"]


def test_time_rotation_dst(freeze_time, tmp_path):
    with freeze_time("2018-10-27 05:00:00", ("CET", 3600)):
        i = logger.add(tmp_path / "test_{time}.log", format="{message}", rotation="1 day")
        logger.debug("First")

        with freeze_time("2018-10-28 05:30:00", ("CEST", 7200)):
            logger.debug("Second")

            with freeze_time("2018-10-29 06:00:00", ("CET", 3600)):
                logger.debug("Third")

    logger.remove(i)

    check_dir(
        tmp_path,
        files=[
            ("test_2018-10-27_05-00-00_000000.log", "First\n"),
            ("test_2018-10-28_05-30-00_000000.log", "Second\n"),
            ("test_2018-10-29_06-00-00_000000.log", "Third\n"),
        ],
    )


@pytest.mark.parametrize("delay", [False, True])
def test_time_rotation_reopening_native(tmp_path_local, delay):

    with tempfile.TemporaryDirectory(dir=str(tmp_path_local)) as test_dir:
        get_ctime, set_ctime = load_ctime_functions()
        test_file = pathlib.Path(test_dir) / "test.txt"
        test_file.touch()
        timestamp_in = 946681200
        set_ctime(str(test_file), timestamp_in)
        timestamp_out = get_ctime(str(test_file))
        if timestamp_in != timestamp_out:
            pytest.skip(
                "The current system does not support getting and setting file creation dates, "
                "the test can't be run."
            )

    filepath = tmp_path_local / "test.log"
    i = logger.add(filepath, format="{message}", delay=delay, rotation="2 s")
    logger.info("1")
    time.sleep(1.5)
    logger.info("2")
    logger.remove(i)
    i = logger.add(filepath, format="{message}", delay=delay, rotation="2 s")
    logger.info("3")

    check_dir(tmp_path_local, size=1)
    assert filepath.read_text() == "1\n2\n3\n"

    time.sleep(1)
    logger.info("4")

    check_dir(tmp_path_local, size=2)
    assert filepath.read_text() == "4\n"

    logger.remove(i)
    time.sleep(1)
    i = logger.add(filepath, format="{message}", delay=delay, rotation="2 s")
    logger.info("5")

    check_dir(tmp_path_local, size=2)
    assert filepath.read_text() == "4\n5\n"

    time.sleep(1.5)
    logger.info("6")
    logger.remove(i)

    check_dir(tmp_path_local, size=3)
    assert filepath.read_text() == "6\n"


@pytest.mark.parametrize("delay", [False, True])
@pytest.mark.skipif(
    os.name == "nt"
    or hasattr(os.stat_result, "st_birthtime")
    or not hasattr(os, "setxattr")
    or not hasattr(os, "getxattr"),
    reason="Testing implementation specific to Linux",
)
def test_time_rotation_reopening_xattr_attributeerror(tmp_path_local, monkeypatch, delay):
    monkeypatch.delattr(os, "setxattr")
    monkeypatch.delattr(os, "getxattr")
    get_ctime, set_ctime = load_ctime_functions()

    monkeypatch.setattr(loguru._file_sink, "get_ctime", get_ctime)
    monkeypatch.setattr(loguru._file_sink, "set_ctime", set_ctime)

    filepath = tmp_path_local / "test.log"
    i = logger.add(filepath, format="{message}", delay=delay, rotation="2 s")
    time.sleep(1)
    logger.info("1")
    logger.remove(i)
    time.sleep(1.5)
    i = logger.add(filepath, format="{message}", delay=delay, rotation="2 s")
    logger.info("2")
    logger.remove(i)
    check_dir(tmp_path_local, size=1)
    assert filepath.read_text() == "1\n2\n"
    time.sleep(2.5)
    i = logger.add(filepath, format="{message}", delay=delay, rotation="2 s")
    logger.info("3")
    logger.remove(i)
    check_dir(tmp_path_local, size=2)
    assert filepath.read_text() == "3\n"


@pytest.mark.parametrize("delay", [False, True])
@pytest.mark.skipif(
    os.name == "nt"
    or hasattr(os.stat_result, "st_birthtime")
    or not hasattr(os, "setxattr")
    or not hasattr(os, "getxattr"),
    reason="Testing implementation specific to Linux",
)
def test_time_rotation_reopening_xattr_oserror(tmp_path_local, monkeypatch, delay):
    monkeypatch.setattr(os, "setxattr", Mock(side_effect=OSError))
    monkeypatch.setattr(os, "getxattr", Mock(side_effect=OSError))
    get_ctime, set_ctime = load_ctime_functions()

    monkeypatch.setattr(loguru._file_sink, "get_ctime", get_ctime)
    monkeypatch.setattr(loguru._file_sink, "set_ctime", set_ctime)

    filepath = tmp_path_local / "test.log"
    i = logger.add(filepath, format="{message}", delay=delay, rotation="2 s")
    time.sleep(1)
    logger.info("1")
    logger.remove(i)
    time.sleep(1.5)
    i = logger.add(filepath, format="{message}", delay=delay, rotation="2 s")
    logger.info("2")
    logger.remove(i)
    check_dir(tmp_path_local, size=1)
    assert filepath.read_text() == "1\n2\n"
    time.sleep(2.5)
    i = logger.add(filepath, format="{message}", delay=delay, rotation="2 s")
    logger.info("3")
    logger.remove(i)
    check_dir(tmp_path_local, size=2)
    assert filepath.read_text() == "3\n"


@pytest.mark.skipif(os.name != "nt", reason="Testing implementation specific to Windows")
def test_time_rotation_windows_no_setctime(tmp_path, monkeypatch):
    import win32_setctime

    monkeypatch.setattr(win32_setctime, "SUPPORTED", False)
    monkeypatch.setattr(win32_setctime, "setctime", Mock())

    filepath = tmp_path / "test.log"
    logger.add(filepath, format="{message}", rotation="2 s")
    logger.info("1")
    time.sleep(1.5)
    logger.info("2")
    check_dir(tmp_path, size=1)
    assert filepath.read_text() == "1\n2\n"
    time.sleep(1)
    logger.info("3")
    check_dir(tmp_path, size=2)
    assert filepath.read_text() == "3\n"

    assert not win32_setctime.setctime.called


@pytest.mark.parametrize("exception", [ValueError, OSError])
@pytest.mark.skipif(os.name != "nt", reason="Testing implementation specific to Windows")
def test_time_rotation_windows_setctime_exception(tmp_path, monkeypatch, exception):
    import win32_setctime

    monkeypatch.setattr(win32_setctime, "setctime", Mock(side_effect=exception))

    filepath = tmp_path / "test.log"
    logger.add(filepath, format="{message}", rotation="2 s")
    logger.info("1")
    time.sleep(1.5)
    logger.info("2")
    check_dir(tmp_path, size=1)
    assert filepath.read_text() == "1\n2\n"
    time.sleep(1)
    logger.info("3")
    check_dir(tmp_path, size=2)
    assert filepath.read_text() == "3\n"

    assert win32_setctime.setctime.called


def test_function_rotation(freeze_time, tmp_path):
    with freeze_time("2018-01-01 00:00:00") as frozen:
        logger.add(
            tmp_path / "test_{time}.log",
            rotation=Mock(side_effect=[False, True, False]),
            format="{message}",
        )
        logger.debug("a")
        check_dir(tmp_path, files=[("test_2018-01-01_00-00-00_000000.log", "a\n")])

        frozen.move_to("2019-01-01 00:00:00")
        logger.debug("b")
        check_dir(
            tmp_path,
            files=[
                ("test_2018-01-01_00-00-00_000000.log", "a\n"),
                ("test_2019-01-01_00-00-00_000000.log", "b\n"),
            ],
        )

        frozen.move_to("2020-01-01 00:00:00")
        logger.debug("c")
        check_dir(
            tmp_path,
            files=[
                ("test_2018-01-01_00-00-00_000000.log", "a\n"),
                ("test_2019-01-01_00-00-00_000000.log", "b\nc\n"),
            ],
        )


@pytest.mark.parametrize("mode", ["w", "x"])
def test_rotation_at_remove(freeze_time, tmp_path, mode):
    with freeze_time("2018-01-01"):
        i = logger.add(
            tmp_path / "test_{time:YYYY}.log",
            rotation="10 MB",
            mode=mode,
            format="{message}",
        )
        logger.debug("test")
        logger.remove(i)

    check_dir(tmp_path, files=[("test_2018.log", "test\n")])


@pytest.mark.parametrize("mode", ["a", "a+"])
def test_no_rotation_at_remove(tmp_path, mode):
    i = logger.add(tmp_path / "test.log", rotation="10 MB", mode=mode, format="{message}")
    logger.debug("test")
    logger.remove(i)

    check_dir(tmp_path, files=[("test.log", "test\n")])


def test_rename_existing_with_creation_time(freeze_time, tmp_path):
    with freeze_time("2018-01-01") as frozen:
        logger.add(tmp_path / "test.log", rotation=10, format="{message}")
        logger.debug("X")
        frozen.tick()
        logger.debug("Y" * 20)

    check_dir(
        tmp_path,
        files=[
            ("test.2018-01-01_00-00-00_000000.log", "X\n"),
            ("test.log", "Y" * 20 + "\n"),
        ],
    )


def test_renaming_rotation_dest_exists(freeze_time, tmp_path):
    with freeze_time("2019-01-02 03:04:05.000006"):
        logger.add(tmp_path / "rotate.log", rotation=Mock(return_value=True), format="{message}")
        logger.info("A")
        logger.info("B")
        logger.info("C")

    check_dir(
        tmp_path,
        files=[
            ("rotate.2019-01-02_03-04-05_000006.log", ""),
            ("rotate.2019-01-02_03-04-05_000006.2.log", "A\n"),
            ("rotate.2019-01-02_03-04-05_000006.3.log", "B\n"),
            ("rotate.log", "C\n"),
        ],
    )


def test_renaming_rotation_dest_exists_with_time(freeze_time, tmp_path):
    with freeze_time("2019-01-02 03:04:05.000006"):
        logger.add(
            tmp_path / "rotate.{time}.log", rotation=Mock(return_value=True), format="{message}"
        )
        logger.info("A")
        logger.info("B")
        logger.info("C")

    check_dir(
        tmp_path,
        files=[
            ("rotate.2019-01-02_03-04-05_000006.2019-01-02_03-04-05_000006.log", ""),
            ("rotate.2019-01-02_03-04-05_000006.2019-01-02_03-04-05_000006.2.log", "A\n"),
            ("rotate.2019-01-02_03-04-05_000006.2019-01-02_03-04-05_000006.3.log", "B\n"),
            ("rotate.2019-01-02_03-04-05_000006.log", "C\n"),
        ],
    )


def test_exception_during_rotation(tmp_path, capsys):
    logger.add(
        tmp_path / "test.log",
        rotation=Mock(side_effect=[Exception("Rotation error"), False]),
        format="{message}",
        catch=True,
    )

    logger.info("A")
    logger.info("B")

    check_dir(tmp_path, files=[("test.log", "B\n")])

    out, err = capsys.readouterr()
    assert out == ""
    assert err.count("Logging error in Loguru Handler") == 1
    assert err.count("Exception: Rotation error") == 1


def test_exception_during_rotation_not_caught(tmp_path, capsys):
    logger.add(
        tmp_path / "test.log",
        rotation=Mock(side_effect=[Exception("Rotation error"), False]),
        format="{message}",
        catch=False,
    )

    with pytest.raises(Exception, match=r"Rotation error"):
        logger.info("A")

    logger.info("B")

    check_dir(tmp_path, files=[("test.log", "B\n")])

    out, err = capsys.readouterr()
    assert out == err == ""


@pytest.mark.parametrize(
    "rotation", [object(), os, datetime.date(2017, 11, 11), datetime.datetime.now(), 1j]
)
def test_invalid_rotation(rotation):
    with pytest.raises(TypeError):
        logger.add("test.log", rotation=rotation)


@pytest.mark.parametrize(
    "rotation",
    [
        "w7",
        "w10",
        "w-1",
        "h",
        "M",
        "w1at13",
        "www",
        "13 at w2",
        "w",
        "K",
        "tufy MB",
        "111.111.111 kb",
        "3 Ki",
        "2017.11.12",
        "11:99",
        "monday at 2017",
        "e days",
        "2 days 8 pouooi",
        "foobar",
        "w5 at [not|a|time]",
        "[not|a|day] at 12:00",
        "__dict__",
    ],
)
def test_unknown_rotation(rotation):
    with pytest.raises(ValueError):
        logger.add("test.log", rotation=rotation)
