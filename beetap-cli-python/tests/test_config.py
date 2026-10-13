"""配置解析测试:时长、.env、优先级。"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from beetap_cli import config
from beetap_cli.errors import CliError


class ParseDurationTest(unittest.TestCase):
    def test_seconds_and_bare_numbers(self):
        self.assertEqual(config.parse_duration("90"), 90.0)
        self.assertEqual(config.parse_duration("20s"), 20.0)
        self.assertAlmostEqual(config.parse_duration("500ms"), 0.5)

    def test_minutes_hours_and_compound(self):
        self.assertEqual(config.parse_duration("5m"), 300.0)
        self.assertEqual(config.parse_duration("1h"), 3600.0)
        self.assertEqual(config.parse_duration("1m30s"), 90.0)
        self.assertEqual(config.parse_duration("1.5m"), 90.0)

    def test_invalid(self):
        for bad in ("", "abc", "5x", "1m!", "-3s"):
            with self.assertRaises(ValueError, msg=bad):
                config.parse_duration(bad)


class ParseEnvFileTest(unittest.TestCase):
    def test_quotes_comments_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "# 注释\n"
                "BEETAP_URL=http://127.0.0.1:9318\n"
                "export BEETAP_MODULE = 'lark-tap'\n"
                'BEETAP_TIMEOUT="6m"  # 行内注释\n'
                "IGNORED_LINE\n",
                encoding="utf-8",
            )
            values = config.parse_env_file(path)
        self.assertEqual(values["BEETAP_URL"], "http://127.0.0.1:9318")
        self.assertEqual(values["BEETAP_MODULE"], "lark-tap")
        self.assertEqual(values["BEETAP_TIMEOUT"], "6m")
        self.assertNotIn("IGNORED_LINE", values)


class LoadConfigTest(unittest.TestCase):
    def _clean_env(self):
        for key in (config.ENV_URL, config.ENV_MODULE, config.ENV_TIMEOUT):
            os.environ.pop(key, None)

    def test_defaults(self):
        self._clean_env()
        with mock.patch.object(config, "find_env_file", return_value=None):
            cfg = config.load()
        self.assertEqual(cfg.url, config.DEFAULT_URL)
        self.assertIsNone(cfg.module)
        self.assertEqual(cfg.timeout, config.DEFAULT_TIMEOUT)

    def test_precedence_flag_over_env(self):
        self._clean_env()
        os.environ[config.ENV_URL] = "http://10.0.0.9:9000"
        os.environ[config.ENV_MODULE] = "env-module"
        os.environ[config.ENV_TIMEOUT] = "30s"
        try:
            with mock.patch.object(config, "find_env_file", return_value=None):
                cfg = config.load(url="http://127.0.0.1:8000", module="flag-module", timeout=99.0)
        finally:
            self._clean_env()
        self.assertEqual(cfg.url, "http://127.0.0.1:8000")
        self.assertEqual(cfg.module, "flag-module")
        self.assertEqual(cfg.timeout, 99.0)

    def test_env_over_env_file(self):
        self._clean_env()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("BEETAP_URL=http://file:1\nBEETAP_MODULE=file-module\n", encoding="utf-8")
            os.environ[config.ENV_URL] = "http://env:2"
            try:
                cfg = config.load(env_file=str(path))
            finally:
                self._clean_env()
        self.assertEqual(cfg.url, "http://env:2")
        self.assertEqual(cfg.module, "file-module")

    def test_env_file_settings(self):
        self._clean_env()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "BEETAP_MODULE=lark-tap\nBEETAP_TIMEOUT=6m\n",
                encoding="utf-8",
            )
            cfg = config.load(env_file=str(path))
        self.assertEqual(cfg.module, "lark-tap")
        self.assertEqual(cfg.timeout, 360.0)

    def test_invalid_url(self):
        self._clean_env()
        with mock.patch.object(config, "find_env_file", return_value=None):
            with self.assertRaises(CliError):
                config.load(url="127.0.0.1:9318")

    def test_invalid_timeout_env(self):
        self._clean_env()
        os.environ[config.ENV_TIMEOUT] = "abc"
        try:
            with mock.patch.object(config, "find_env_file", return_value=None):
                with self.assertRaises(CliError):
                    config.load()
        finally:
            self._clean_env()


class FindEnvFileTest(unittest.TestCase):
    """查找规则:跳过不含已知键的文件(空文件不遮蔽后面的配置)。"""

    def test_skips_files_without_known_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty = root / "empty.env"
            empty.write_text("", encoding="utf-8")
            real = root / "real.env"
            real.write_text("BEETAP_MODULE=lark-tap\n", encoding="utf-8")
            with mock.patch.object(config, "env_search_paths", return_value=[empty, real]):
                self.assertEqual(config.find_env_file(), real)

    def test_returns_first_existing_when_no_known_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unrelated = root / "a.env"
            unrelated.write_text("FOO=1\n", encoding="utf-8")
            with mock.patch.object(config, "env_search_paths", return_value=[unrelated]):
                self.assertEqual(config.find_env_file(), unrelated)

    def test_first_with_known_keys_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.env"
            first.write_text("BEETAP_URL=http://a:1\n", encoding="utf-8")
            second = root / "second.env"
            second.write_text("BEETAP_MODULE=lark-tap\n", encoding="utf-8")
            with mock.patch.object(config, "env_search_paths", return_value=[first, second]):
                self.assertEqual(config.find_env_file(), first)


if __name__ == "__main__":
    unittest.main()
