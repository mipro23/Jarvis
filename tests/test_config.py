"""Тесты единого модуля настроек config.py.

Запуск: .venv/Scripts/python.exe -m unittest tests.test_config -v
Тесты подменяют папку настроек на временную и не трогают реальный %APPDATA%.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config


class TempConfigDir(unittest.TestCase):
    """Базовый класс: папка настроек указывает во временную директорию."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.tmp.name)
        patcher = mock.patch.object(
            config, "get_config_dir", return_value=self.config_dir
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def config_file(self):
        return self.config_dir / "config.json"

    def write_config(self, text):
        self.config_file().write_text(text, encoding="utf-8")


class LoadConfigTests(TempConfigDir):
    def test_missing_file_returns_defaults(self):
        cfg = config.load_config()
        self.assertEqual(cfg["wake_word"], config.DEFAULTS["wake_word"])
        self.assertEqual(cfg["mic_device"], None)
        self.assertEqual(cfg["ollama_model"], "qwen2.5:7b")
        self.assertIsNone(config.config_problem())

    def test_old_cloud_config_gets_new_defaults(self):
        self.write_config(json.dumps({
            "cloud_enabled": True,
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b",
            "api_key": "secret",
        }))
        cfg = config.load_config()
        self.assertEqual(cfg["api_key"], "secret")          # старое сохранено
        self.assertEqual(cfg["model"], "llama-3.3-70b")
        self.assertEqual(cfg["wake_word"], "джарвис")        # новое по умолчанию
        self.assertEqual(cfg["voice_model"], "ru_RU-irina-medium.onnx")
        self.assertIsNone(config.config_problem())

    def test_unknown_user_keys_preserved(self):
        self.write_config(json.dumps({"my_own_flag": 42}))
        cfg = config.load_config()
        self.assertEqual(cfg["my_own_flag"], 42)

    def test_empty_file_is_reported_not_silent(self):
        self.write_config("")
        cfg = config.load_config()
        self.assertEqual(cfg["wake_word"], "джарвис")
        self.assertIsNotNone(config.config_problem())

    def test_corrupted_json_reported_and_file_untouched(self):
        self.write_config("{это не json")
        cfg = config.load_config()
        self.assertEqual(cfg["wake_word"], "джарвис")
        problem = config.config_problem()
        self.assertIsNotNone(problem)
        self.assertIn("повреждён", problem)
        # Файл не перезаписан в момент загрузки.
        self.assertEqual(self.config_file().read_text(encoding="utf-8"), "{это не json")

    def test_non_dict_root_reported(self):
        self.write_config("[1, 2, 3]")
        config.load_config()
        self.assertIsNotNone(config.config_problem())

    def test_type_coercion(self):
        self.write_config(json.dumps({"mic_device": "2", "max_tokens": "500"}))
        cfg = config.load_config()
        self.assertEqual(cfg["mic_device"], 2)
        self.assertEqual(cfg["max_tokens"], 500)
        self.write_config(json.dumps({"mic_device": "мусор", "max_tokens": []}))
        cfg = config.load_config()
        self.assertIsNone(cfg["mic_device"])
        self.assertEqual(cfg["max_tokens"], config.DEFAULTS["max_tokens"])


class SaveConfigTests(TempConfigDir):
    def test_save_merges_without_losing_keys(self):
        self.write_config(json.dumps({
            "api_key": "secret",
            "wake_word": "дом",
            "my_own_flag": 42,
        }, ensure_ascii=False))
        merged, backup = config.save_config({"mic_device": 1})
        self.assertIsNone(backup)
        data = json.loads(self.config_file().read_text(encoding="utf-8"))
        self.assertEqual(data["api_key"], "secret")
        self.assertEqual(data["wake_word"], "дом")
        self.assertEqual(data["my_own_flag"], 42)
        self.assertEqual(data["mic_device"], 1)
        self.assertEqual(merged["mic_device"], 1)

    def test_save_on_corrupted_file_creates_backup(self):
        self.write_config("{повреждено")
        _, backup = config.save_config({"wake_word": "джарвис"})
        self.assertIsNotNone(backup)
        self.assertTrue(Path(backup).exists())
        self.assertEqual(Path(backup).read_text(encoding="utf-8"), "{повреждено")
        data = json.loads(self.config_file().read_text(encoding="utf-8"))
        self.assertEqual(data["wake_word"], "джарвис")
        self.assertIsNone(config.config_problem())

    def test_save_is_utf8_and_atomic(self):
        _, _ = config.save_config({"wake_word": "джарвис"})
        raw = self.config_file().read_text(encoding="utf-8")
        self.assertIn("джарвис", raw)                        # не \u-последовательности
        leftovers = [p.name for p in self.config_dir.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_missing_file_save_creates_dir_and_file(self):
        self.config_dir = self.config_dir / "nested" / "Jarvis"
        with mock.patch.object(config, "get_config_dir", return_value=self.config_dir):
            merged, backup = config.save_config({"mic_device": 3})
        self.assertIsNone(backup)
        data = json.loads(self.config_file().read_text(encoding="utf-8"))
        self.assertEqual(data["mic_device"], 3)
        self.assertEqual(merged["ollama_model"], config.DEFAULTS["ollama_model"])


class ResolveVoiceModelTests(TempConfigDir):
    def setUp(self):
        super().setUp()
        app_dir = tempfile.TemporaryDirectory()
        self.addCleanup(app_dir.cleanup)
        self.app_dir = Path(app_dir.name)
        patcher = mock.patch.object(config, "APP_DIR", self.app_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_relative_name_found_next_to_program(self):
        (self.app_dir / "voice.onnx").write_bytes(b"x")
        path, error = config.resolve_voice_model({"voice_model": "voice.onnx"})
        self.assertIsNone(error)
        self.assertEqual(path, self.app_dir / "voice.onnx")

    def test_absolute_path_used_as_is(self):
        target = self.app_dir / "abs.onnx"
        target.write_bytes(b"x")
        path, error = config.resolve_voice_model({"voice_model": str(target)})
        self.assertIsNone(error)
        self.assertEqual(path, target)

    def test_missing_model_gives_clear_error(self):
        path, error = config.resolve_voice_model({"voice_model": "nope.onnx"})
        self.assertIsNone(path)
        self.assertIsNotNone(error)
        self.assertIn("не найдена", error)
        self.assertIn("nope.onnx", error)
        self.assertIn(str(self.app_dir / "nope.onnx"), error)
        self.assertIn(str(self.config_dir / "nope.onnx"), error)

    def test_empty_value_falls_back_to_default_name(self):
        (self.app_dir / config.DEFAULTS["voice_model"]).write_bytes(b"x")
        path, error = config.resolve_voice_model({"voice_model": ""})
        self.assertIsNone(error)
        self.assertEqual(path.name, config.DEFAULTS["voice_model"])


class MicrophoneTests(TempConfigDir):
    DEVICES = [
        {"index": 0, "max_input_channels": 2, "name": "Микрофон (Realtek)"},
        {"index": 1, "max_input_channels": 0, "name": "Динамики"},
        {"index": 3, "max_input_channels": 1, "name": "USB-микрофон"},
    ]

    def test_valid_device_selected(self):
        device, warning = config.select_microphone({"mic_device": 3}, self.DEVICES)
        self.assertEqual(device, 3)
        self.assertIsNone(warning)

    def test_missing_device_falls_back_to_default_with_listing(self):
        device, warning = config.select_microphone({"mic_device": 7}, self.DEVICES)
        self.assertIsNone(device)                     # выдуманный индекс не подставляется
        self.assertIsNotNone(warning)
        self.assertIn("№7", warning)
        self.assertIn("Микрофон (Realtek)", warning)
        self.assertIn("USB-микрофон", warning)
        self.assertNotIn("Динамики", warning)         # выводные устройства не предлагаются

    def test_none_uses_default_silently(self):
        device, warning = config.select_microphone({"mic_device": None}, self.DEVICES)
        self.assertIsNone(device)
        self.assertIsNone(warning)


class WakeWordTests(TempConfigDir):
    def test_default_wake_word(self):
        self.assertEqual(config.get_wake_words({}), ["джарвис"])

    def test_case_and_yo_and_several_words(self):
        words = config.get_wake_words({"wake_word": "Джарвис, Ёлка"})
        self.assertEqual(words, ["джарвис", "елка"])

    def test_garbage_falls_back_to_default(self):
        self.assertEqual(config.get_wake_words({"wake_word": "  "}), ["джарвис"])


class ValidateConfigTests(TempConfigDir):
    def test_cloud_enabled_without_credentials_warns(self):
        warnings = config.validate_config({"cloud_enabled": True, "api_key": ""})
        self.assertTrue(any("API-ключ" in w for w in warnings))

    def test_valid_config_has_no_warnings(self):
        warnings = config.validate_config({
            "wake_word": "джарвис",
            "ollama_model": "qwen2.5:7b",
            "cloud_enabled": False,
            "max_tokens": 700,
        })
        self.assertEqual(warnings, [])


class ImportIndependenceTests(unittest.TestCase):
    def test_imports_from_foreign_cwd(self):
        """Импорт config не должен зависеть от текущей рабочей папки."""
        result = subprocess.run(
            [sys.executable, "-c",
             f"import sys; sys.path.insert(0, {str(config.APP_DIR)!r}); "
             f"import config; print(config.get_config_path())"],
            capture_output=True,
            text=True,
            cwd=tempfile.gettempdir(),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("config.json", result.stdout)

    def test_config_has_no_project_imports(self):
        source = Path(config.__file__).read_text(encoding="utf-8")
        for forbidden in ("import main", "import gui", "from main", "from gui"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
