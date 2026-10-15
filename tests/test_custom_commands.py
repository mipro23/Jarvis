"""Тесты сопоставления пользовательских команд и обработки ошибок конфигурации.

Запуск: .venv/Scripts/python.exe -m unittest tests.test_custom_commands -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main


class LoadCustomCommandsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        main.CUSTOM_COMMANDS_FILE = Path(self.tmp.name) / "custom_commands.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, content):
        main.CUSTOM_COMMANDS_FILE.write_text(content, encoding="utf-8")

    def test_valid_file(self):
        self.write(json.dumps([{"phrase": "роблокс", "action": "open_app", "target": "x"}], ensure_ascii=False))
        data = main.load_custom_commands()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["phrase"], "роблокс")

    def test_missing_file(self):
        data = main.load_custom_commands()
        self.assertEqual(data, [])

    def test_empty_file(self):
        self.write("")
        self.assertEqual(main.load_custom_commands(), [])

    def test_corrupted_json(self):
        self.write("{это не json")
        self.assertEqual(main.load_custom_commands(), [])

    def test_non_dict_items_skipped(self):
        self.write('["строка", 42, {"phrase": "дота", "action": "open_app", "target": "steam://rungameid/570"}]')
        data = main.load_custom_commands()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["phrase"], "дота")

    def test_not_a_list(self):
        self.write('{"phrase": "дота"}')
        self.assertEqual(main.load_custom_commands(), [])


class MatchCustomCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        main.CUSTOM_COMMANDS_FILE = Path(self.tmp.name) / "custom_commands.json"
        self.write([
            {"phrase": "роблокс", "action": "open_app", "target": "roblox.exe"},
            {"phrase": "включи доту", "action": "open_app", "target": "steam://rungameid/570"},
            {"phrase": "телемост", "action": "open_site", "target": "https://telemost.yandex.ru/"},
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        main.CUSTOM_COMMANDS_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_exact_match(self):
        cmd = main.match_custom_command("роблокс")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd["phrase"], "роблокс")

    def test_embedded_match(self):
        cmd = main.match_custom_command("алиска включи доту пожалуйста")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd["phrase"], "включи доту")

    def test_case_and_yo_normalized(self):
        self.write([{"phrase": "ёлка", "action": "say", "target": "привет"}])
        self.assertIsNotNone(main.match_custom_command("ЁЛКА"))

    def test_longer_phrase_wins(self):
        self.write([
            {"phrase": "дота", "action": "open_app", "target": "steam://rungameid/570"},
            {"phrase": "включи доту", "action": "open_site", "target": "https://steamcommunity.com"},
        ])
        cmd = main.match_custom_command("включи доту")
        self.assertEqual(cmd["phrase"], "включи доту")

    def test_no_match(self):
        self.assertIsNone(main.match_custom_command("сделай скриншот"))

    def test_empty_text(self):
        self.assertIsNone(main.match_custom_command(""))

    def test_broken_file_means_no_match(self):
        main.CUSTOM_COMMANDS_FILE.write_text("[повреждено", encoding="utf-8")
        self.assertIsNone(main.match_custom_command("роблокс"))


class RunCustomCommandErrorTests(unittest.TestCase):
    """Проверяем только ветки ошибок, которые ничего не запускают на системе."""

    def test_open_app_empty_target(self):
        answer = main.run_custom_command({"action": "open_app", "target": ""}, None)
        self.assertIn("не указано приложение", answer)

    def test_open_site_empty_target(self):
        answer = main.run_custom_command({"action": "open_site", "target": ""}, None)
        self.assertIn("не указан адрес", answer)

    def test_say_empty_target(self):
        answer = main.run_custom_command({"action": "say", "target": ""}, None)
        self.assertIn("не задан текст", answer)

    def test_unknown_action(self):
        answer = main.run_custom_command({"action": "format_disk", "target": "C:\\"}, None)
        self.assertIn("Неизвестное действие", answer)

    def test_disallowed_hotkey(self):
        answer = main.run_custom_command({"action": "hotkey", "target": "ctrl+alt+del"}, None)
        self.assertIn("не разрешено", answer)


if __name__ == "__main__":
    unittest.main()
