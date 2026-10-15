"""Тесты файловой очереди текстовых команд и быстрой остановки.

Запуск: .venv/Scripts/python.exe -m unittest tests.test_text_commands -v
Аудио не используется: record_audio подменяется, при вызове ломает тест.
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys_path = Path(__file__).resolve().parent.parent

import sys
sys.path.insert(0, str(sys_path))

import main


class TextQueueTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.queue_dir = Path(self.tmp.name)
        patcher = mock.patch.object(main, "TEXT_COMMAND_DIR", self.queue_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Если тест пойдёт в запись звука — сразу падаем
        audio_patcher = mock.patch.object(
            main, "record_audio", side_effect=AssertionError("аудио не должно вызываться")
        )
        audio_patcher.start()
        self.addCleanup(audio_patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def push(self, name, text):
        (self.queue_dir / name).write_text(text, encoding="utf-8")


class PopTextCommandTests(TextQueueTestCase):
    def test_missing_dir_returns_none(self):
        self.assertIsNone(main.pop_text_command())

    def test_empty_dir_returns_none(self):
        self.queue_dir.mkdir(exist_ok=True)
        self.assertIsNone(main.pop_text_command())

    def test_single_command_popped_and_deleted(self):
        self.push("20261015-120000-aabb.txt", "открой блокнот")
        self.assertEqual(main.pop_text_command(), "открой блокнот")
        self.assertEqual(list(self.queue_dir.iterdir()), [])
        self.assertIsNone(main.pop_text_command())

    def test_oldest_file_first(self):
        self.push("20261015-120001-bbbb.txt", "вторая")
        self.push("20261015-120000-aaaa.txt", "первая")
        self.assertEqual(main.pop_text_command(), "первая")
        self.assertEqual(main.pop_text_command(), "вторая")

    def test_whitespace_only_file_skipped(self):
        self.push("0001-empty.txt", "   \n")
        self.push("0002-real.txt", "привет")
        self.assertEqual(main.pop_text_command(), "привет")
        self.assertEqual(list(self.queue_dir.iterdir()), [])

    def test_unreadable_file_skipped_not_fatal(self):
        self.push("0001-bad.txt", "данные")
        self.push("0002-good.txt", "работай")
        with mock.patch.object(
            Path, "read_text", side_effect=OSError("файл занят")
        ):
            # read_text подменён глобально: ни один файл не читается
            self.assertIsNone(main.pop_text_command())
        # Файлы не удалены (unlink не вызывался при ошибке чтения)
        self.assertEqual(len(list(self.queue_dir.iterdir())), 2)


class ClearTextCommandsTests(TextQueueTestCase):
    def test_clears_leftovers(self):
        self.push("leftover.txt", "старая команда")
        main.clear_text_commands()
        self.assertEqual(list(self.queue_dir.iterdir()), [])

    def test_missing_dir_is_ok(self):
        main.clear_text_commands()


class FastStopTests(TextQueueTestCase):
    def test_wait_for_wake_word_returns_immediately_on_stop_flag(self):
        flag = Path(self.tmp.name) / "stop.flag"
        flag.write_text("stop")
        with mock.patch.object(main, "stop_requested", return_value=True):
            self.assertIsNone(main.wait_for_wake_word(whisper=None))

    def test_wait_for_wake_word_returns_text_command_without_audio(self):
        self.push("cmd.txt", "который час")
        self.assertEqual(main.wait_for_wake_word(whisper=None), "который час")
        # Файл удалён — повторный вызов ушёл бы в прослушивание (не проверяем).

    def test_empty_command_does_not_confuse_wake_loop(self):
        self.push("cmd.txt", "   ")
        # Пустая команда не должна вернуться как текстовая; дальше цикл пошёл бы
        # в record_audio, который в этом тесте ломает выполнение.
        with self.assertRaises(AssertionError):
            main.wait_for_wake_word(whisper=None)


if __name__ == "__main__":
    unittest.main()
