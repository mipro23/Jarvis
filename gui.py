
import sys
import os
import json
from datetime import datetime

from PySide6.QtCore import Qt, QProcess, QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QFrame,
    QSizePolicy,
    QDialog,
    QListWidget,
    QLineEdit,
    QComboBox,
    QFormLayout,
    QMessageBox,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_FILE = os.path.join(BASE_DIR, "main.py")
PYTHON_EXE = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
STOP_FLAG = os.path.join(BASE_DIR, "jarvis_stop.flag")
CUSTOM_COMMANDS_FILE = os.path.join(BASE_DIR, "custom_commands.json")


class CustomCommandsDialog(QDialog):
    """Редактор пользовательских голосовых команд, хранящихся в JSON."""
    ACTIONS = [
        ("Открыть приложение", "open_app"),
        ("Открыть сайт", "open_site"),
        ("Нажать сочетание клавиш", "hotkey"),
        ("Сказать фразу голосом", "say"),
        ("Свернуть активное окно", "minimize_window"),
        ("Развернуть активное окно", "maximize_window"),
        ("Переключить окно", "switch_window"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Мои голосовые команды")
        self.resize(620, 500)
        self.commands = self.load_commands()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Создай фразу, которую Алиса должна услышать после имени, и выбери действие."))
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self.select_command)
        layout.addWidget(self.list_widget, 1)

        form = QFormLayout()
        self.phrase_input = QLineEdit()
        self.phrase_input.setPlaceholderText("например: включи рабочий режим")
        form.addRow("Что услышать:", self.phrase_input)

        self.action_combo = QComboBox()
        for label, value in self.ACTIONS:
            self.action_combo.addItem(label, value)
        self.action_combo.currentIndexChanged.connect(self.update_target_hint)
        form.addRow("Что сделать:", self.action_combo)

        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("например: calculator")
        form.addRow("Параметр действия:", self.target_input)
        layout.addLayout(form)

        hint = QLabel(
            "Параметры: приложение — notepad / calculator / explorer / browser; "
            "сайт — google / youtube / wikipedia; сочетание — например ctrl+shift+esc; "
            "фраза — произвольный текст. Для действий без параметра оставь поле пустым."
        )
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        self.new_button = QPushButton("＋ Новая")
        self.new_button.clicked.connect(self.new_command)
        buttons.addWidget(self.new_button)
        self.save_button = QPushButton("Сохранить команду")
        self.save_button.clicked.connect(self.save_current)
        buttons.addWidget(self.save_button)
        self.delete_button = QPushButton("Удалить")
        self.delete_button.clicked.connect(self.delete_current)
        buttons.addWidget(self.delete_button)
        layout.addLayout(buttons)

        self.refresh_list()
        self.update_target_hint()

    def load_commands(self):
        try:
            with open(CUSTOM_COMMANDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def write_commands(self):
        with open(CUSTOM_COMMANDS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.commands, f, ensure_ascii=False, indent=2)

    def refresh_list(self, selected=0):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for item in self.commands:
            self.list_widget.addItem(f"{item.get('phrase', '')}  →  {item.get('action', '')}")
        self.list_widget.blockSignals(False)
        if self.commands:
            selected = max(0, min(selected, len(self.commands) - 1))
            self.list_widget.setCurrentRow(selected)
        else:
            self.new_command()

    def select_command(self, row):
        if row < 0 or row >= len(self.commands):
            return
        item = self.commands[row]
        self.phrase_input.setText(item.get("phrase", ""))
        idx = self.action_combo.findData(item.get("action", "say"))
        self.action_combo.setCurrentIndex(max(0, idx))
        self.target_input.setText(item.get("target", ""))

    def new_command(self):
        self.list_widget.setCurrentRow(-1)
        self.list_widget.clearSelection()
        self.phrase_input.clear()
        self.action_combo.setCurrentIndex(0)
        self.target_input.clear()
        self.phrase_input.setFocus()

    def update_target_hint(self, *_):
        action = self.action_combo.currentData()
        hints = {
            "open_app": "notepad / calculator / explorer / browser",
            "open_site": "google / youtube / wikipedia",
            "hotkey": "например ctrl+shift+esc (только разрешённые сочетания)",
            "say": "фраза, которую Алиса произнесёт",
            "minimize_window": "не требуется",
            "maximize_window": "не требуется",
            "switch_window": "не требуется",
        }
        self.target_input.setPlaceholderText(hints.get(action, ""))

    def save_current(self):
        phrase = " ".join(self.phrase_input.text().strip().lower().split())
        action = self.action_combo.currentData()
        target = self.target_input.text().strip()
        if not phrase:
            QMessageBox.warning(self, "Не хватает фразы", "Заполни поле «Что услышать».")
            return
        if action in ("open_app", "open_site", "hotkey", "say") and not target:
            QMessageBox.warning(self, "Не хватает параметра", "Заполни поле «Параметр действия».")
            return
        row = self.list_widget.currentRow()
        entry = {"phrase": phrase, "action": action, "target": target}
        if 0 <= row < len(self.commands):
            self.commands[row] = entry
            selected = row
        else:
            self.commands.append(entry)
            selected = len(self.commands) - 1
        try:
            self.write_commands()
        except OSError as exc:
            QMessageBox.critical(self, "Ошибка сохранения", str(exc))
            return
        self.refresh_list(selected)
        QMessageBox.information(self, "Готово", "Команда сохранена. Она будет доступна после следующего распознавания.")

    def delete_current(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.commands):
            return
        self.commands.pop(row)
        try:
            self.write_commands()
        except OSError as exc:
            QMessageBox.critical(self, "Ошибка сохранения", str(exc))
            return
        self.refresh_list(max(0, row - 1))


class JarvisGUI(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("JARVIS — Локальный помощник")
        self.resize(1100, 720)
        self.setMinimumSize(850, 580)

        self.process = QProcess(self)
        self.process.setWorkingDirectory(BASE_DIR)
        self.process.setProcessChannelMode(
            QProcess.ProcessChannelMode.MergedChannels
        )

        self.output_buffer = ""
        self.assistant_ready = False
        self.stopping = False

        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.started.connect(self.on_started)
        self.process.finished.connect(self.on_finished)
        self.process.errorOccurred.connect(self.on_process_error)

        self.build_ui()
        self.apply_style()

        self.add_chat(
            "СИСТЕМА",
            "Интерфейс готов. Нажми «Запустить Джарвиса».",
            "#8796ad",
        )

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        # Левая панель
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(235)

        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 22, 18, 18)
        side.setSpacing(14)

        logo = QLabel("J.A.R.V.I.S.")
        logo.setObjectName("logo")

        subtitle = QLabel("ЛОКАЛЬНЫЙ ИИ-ПОМОЩНИК")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)

        side.addWidget(logo)
        side.addWidget(subtitle)
        side.addSpacing(18)

        side.addWidget(self.make_section_label("СОСТОЯНИЕ"))

        self.status_label = QLabel("ОСТАНОВЛЕН")
        self.status_label.setObjectName("statusStopped")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setMinimumHeight(42)
        side.addWidget(self.status_label)

        self.process_label = QLabel("Процесс: не запущен")
        self.process_label.setObjectName("muted")
        self.process_label.setWordWrap(True)
        side.addWidget(self.process_label)

        side.addSpacing(12)
        side.addWidget(self.make_section_label("УПРАВЛЕНИЕ"))

        self.start_button = QPushButton("▶  Запустить Джарвиса")
        self.start_button.setObjectName("startButton")
        self.start_button.clicked.connect(self.start_jarvis)
        side.addWidget(self.start_button)

        self.stop_button = QPushButton("■  Остановить")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.clicked.connect(self.stop_jarvis)
        self.stop_button.setEnabled(False)
        side.addWidget(self.stop_button)

        self.clear_button = QPushButton("⌫  Очистить чат")
        self.clear_button.clicked.connect(self.clear_chat)
        side.addWidget(self.clear_button)

        self.commands_button = QPushButton("⚙  Мои команды")
        self.commands_button.clicked.connect(self.open_custom_commands)
        side.addWidget(self.commands_button)

        side.addStretch()

        note = QLabel(
            "Голосовое распознавание и ответы отображаются здесь, "
            "если main.py выводит их в консоль."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        side.addWidget(note)

        root.addWidget(sidebar)

        # Основная панель
        main_panel = QVBoxLayout()
        main_panel.setSpacing(14)
        root.addLayout(main_panel, 1)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(22, 16, 22, 16)

        heading = QLabel("Центр управления")
        heading.setObjectName("heading")

        description = QLabel(
            "Голосовой канал · Распознавание речи · Ответы ассистента"
        )
        description.setObjectName("muted")

        header_layout.addWidget(heading)
        header_layout.addWidget(description)
        main_panel.addWidget(header)

        # Карточки состояния
        cards = QHBoxLayout()
        cards.setSpacing(12)

        self.card_state = self.make_card("СОСТОЯНИЕ", "Остановлен")
        self.card_voice = self.make_card("ГОЛОС", "Ожидание")
        self.card_model = self.make_card("МОДЕЛЬ", "Локальная")

        cards.addWidget(self.card_state)
        cards.addWidget(self.card_voice)
        cards.addWidget(self.card_model)

        main_panel.addLayout(cards)

        # Чат
        chat_frame = QFrame()
        chat_frame.setObjectName("chatFrame")
        chat_layout = QVBoxLayout(chat_frame)
        chat_layout.setContentsMargins(16, 14, 16, 14)
        chat_layout.setSpacing(10)

        chat_header = QHBoxLayout()

        chat_title = QLabel("Чат и журнал событий")
        chat_title.setObjectName("sectionTitle")

        self.message_count = QLabel("Сообщений: 0")
        self.message_count.setObjectName("muted")

        chat_header.addWidget(chat_title)
        chat_header.addStretch()
        chat_header.addWidget(self.message_count)

        chat_layout.addLayout(chat_header)

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setAcceptRichText(True)
        self.chat.setObjectName("chat")
        self.chat.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        chat_layout.addWidget(self.chat, 1)

        main_panel.addWidget(chat_frame, 1)

        footer = QLabel(
            "JARVIS LOCAL  •  Вывод main.py отображается в чате"
        )
        footer.setObjectName("muted")
        main_panel.addWidget(footer)

        self.message_total = 0

    def make_section_label(self, text):
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def make_card(self, title, value):
        card = QFrame()
        card.setObjectName("card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("muted")

        value_label = QLabel(value)
        value_label.setObjectName("cardValue")

        layout.addWidget(title_label)
        layout.addWidget(value_label)

        card.value_label = value_label
        return card

    def apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #0b1020;
                color: #e8eefc;
                font-family: "Segoe UI";
                font-size: 10pt;
            }

            #sidebar, #header, #chatFrame, #card {
                background-color: #121a2d;
                border: 1px solid #202d47;
                border-radius: 14px;
            }

            #logo {
                color: #67d8ff;
                font-size: 23pt;
                font-weight: 800;
            }

            #heading {
                font-size: 19pt;
                font-weight: 700;
            }

            #sectionTitle {
                font-size: 12pt;
                font-weight: 700;
            }

            #sectionLabel {
                color: #7084a8;
                font-size: 9pt;
                font-weight: 700;
            }

            #muted {
                color: #8291ad;
                font-size: 9pt;
            }

            #statusStopped, #statusLoading, #statusReady {
                border-radius: 9px;
                padding: 9px;
                font-weight: 800;
            }

            #statusStopped {
                color: #ff8585;
                background-color: #351e2b;
            }

            #statusLoading {
                color: #ffd479;
                background-color: #382e1e;
            }

            #statusReady {
                color: #73efb1;
                background-color: #15372f;
            }

            #cardValue {
                color: #67d8ff;
                font-size: 13pt;
                font-weight: 700;
            }

            QPushButton {
                background-color: #1b2740;
                border: 1px solid #2a3a5b;
                border-radius: 9px;
                padding: 11px;
                text-align: left;
                color: #e8eefc;
                font-weight: 600;
            }

            QPushButton:hover {
                background-color: #263856;
                border-color: #67d8ff;
            }

            QPushButton:disabled {
                color: #58647c;
                background-color: #141c2e;
                border-color: #20283b;
            }

            #startButton {
                background-color: #124b50;
                border-color: #1b777a;
            }

            #startButton:hover {
                background-color: #176166;
            }

            #stopButton {
                background-color: #432431;
                border-color: #663343;
            }

            #stopButton:hover {
                background-color: #5b2c3d;
            }

            #chat {
                background-color: #0b1222;
                border: 1px solid #202d47;
                border-radius: 9px;
                padding: 10px;
                color: #e8eefc;
                selection-background-color: #245b79;
                font-family: "Consolas";
                font-size: 10pt;
            }
        """)

    def add_chat(self, speaker, message, color="#e8eefc"):
        message = str(message).strip()
        if not message:
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        safe_speaker = self.html_escape(speaker)
        safe_message = self.html_escape(message).replace("\n", "<br>")

        cursor = self.chat.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        html = (
            f'<p style="margin: 7px 0 2px 0;">'
            f'<span style="color:#71809d;">[{timestamp}]</span> '
            f'<b style="color:{color};">{safe_speaker}</b>'
            f'</p>'
            f'<p style="margin: 0 0 9px 0; color:#e8eefc;">'
            f'{safe_message}</p>'
        )

        cursor.insertHtml(html)
        self.chat.setTextCursor(cursor)
        self.chat.ensureCursorVisible()

        self.message_total += 1
        self.message_count.setText(f"Сообщений: {self.message_total}")

    @staticmethod
    def html_escape(text):
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def set_status(self, text, state):
        self.status_label.setText(text)
        self.status_label.setObjectName(state)

        # Обновляем стиль после смены состояния
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

        self.card_state.value_label.setText(text.capitalize())

    def start_jarvis(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.add_chat("СИСТЕМА", "Джарвис уже запущен.", "#ffd479")
            return

        if not os.path.isfile(MAIN_FILE):
            self.add_chat(
                "ОШИБКА",
                f"Не найден файл: {MAIN_FILE}",
                "#ff8585",
            )
            return

        if not os.path.isfile(PYTHON_EXE):
            self.add_chat(
                "ОШИБКА",
                f"Не найден Python из виртуального окружения: {PYTHON_EXE}",
                "#ff8585",
            )
            return

        try:
            if os.path.exists(STOP_FLAG):
                os.remove(STOP_FLAG)
        except OSError as exc:
            self.add_chat(
                "ПРЕДУПРЕЖДЕНИЕ",
                f"Не удалось удалить stop-файл: {exc}",
                "#ffd479",
            )

        # Явно задаём домашнюю папку Windows и кеш Hugging Face.
        # Это предотвращает RuntimeError: Could not determine home directory.
        home_dir = r"C:\Users\home"
        hf_cache_dir = os.path.join(BASE_DIR, "hf_cache")
        try:
            os.makedirs(hf_cache_dir, exist_ok=True)
        except OSError as exc:
            self.add_chat(
                "ПРЕДУПРЕЖДЕНИЕ",
                f"Не удалось создать папку кеша {hf_cache_dir}: {exc}",
                "#ffd479",
            )

        env = self.process.processEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("USERPROFILE", home_dir)
        env.insert("HOME", home_dir)
        env.insert("HOMEDRIVE", "C:")
        env.insert("HOMEPATH", r"\Users\home")
        env.insert("HF_HOME", hf_cache_dir)
        env.insert("HUGGINGFACE_HUB_CACHE", os.path.join(hf_cache_dir, "hub"))
        self.process.setProcessEnvironment(env)

        self.output_buffer = ""
        self.assistant_ready = False
        self.stopping = False

        self.set_status("ЗАПУСК...", "statusLoading")
        self.card_voice.value_label.setText("Инициализация")
        self.card_model.value_label.setText("Загрузка модели")
        self.process_label.setText("Процесс: запускается")

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.add_chat("СИСТЕМА", "Запускаю main.py...", "#67d8ff")

        self.process.start(PYTHON_EXE, ["-u", MAIN_FILE])

    def on_started(self):
        self.process_label.setText("Процесс: работает")
        self.set_status("ЗАГРУЗКА", "statusLoading")
        self.add_chat(
            "СИСТЕМА",
            "Процесс запущен. Ожидаю готовности голосового помощника.",
            "#67d8ff",
        )

    def read_output(self):
        data = bytes(self.process.readAllStandardOutput())
        if not data:
            return

        decoded = data.decode("utf-8", errors="replace")
        self.output_buffer += decoded

        while "\n" in self.output_buffer:
            line, self.output_buffer = self.output_buffer.split("\n", 1)
            self.handle_assistant_line(line.rstrip("\r"))

    def handle_assistant_line(self, line):
        line = line.strip()
        if not line:
            return

        lower = line.lower()

        # Сообщения о готовности — статус меняется на ГОТОВА
        if (
            "джарвис готов" in lower
            or "алиска готова" in lower
            or "алиска готов" in lower
            or "jarvis ready" in lower
            or "assistant ready" in lower
        ):
            self.assistant_ready = True
            self.set_status("ГОТОВА", "statusReady")
            self.card_voice.value_label.setText("Ожидание команды")
            self.card_model.value_label.setText("Загружена")
            self.add_chat("СИСТЕМА", line, "#73efb1")
            return

        # Текст распознанной речи
        if lower.startswith(("слышу:", "услышала:", "wake:", "wake word:")):
            self.card_voice.value_label.setText("Слушает")
            self.add_chat("🎙️ АЛИСКА УСЛЫШАЛА", line.split(":", 1)[-1], "#67d8ff")
            return

        if lower.startswith(("ты:", "пользователь:", "распознано:", "распознано:")):
            self.card_voice.value_label.setText("Речь распознана")
            self.add_chat("🧑 ТЫ", line.split(":", 1)[-1], "#d8a5ff")
            return

        if lower.startswith(("алиска:", "джарвис:", "jarvis:", "assistant:")):
            self.add_chat("🤖 ДЖАРВИС", line.split(":", 1)[-1], "#73efb1")
            return

        if "загружа" in lower or "инициализац" in lower:
            self.set_status("ЗАГРУЗКА", "statusLoading")
            self.add_chat("СИСТЕМА", line, "#ffd479")
            return

        if "ошибка" in lower or "error" in lower or "traceback" in lower:
            self.add_chat("ОШИБКА", line, "#ff8585")
            return

        if "не удалось распознать" in lower:
            self.card_voice.value_label.setText("Не распознано")
            self.add_chat("🎙️ РАСПОЗНАВАНИЕ", line, "#ffd479")
            return

        # Остальные сообщения тоже не теряем
        self.add_chat("ЖУРНАЛ", line, "#a9b8d4")

    def stop_jarvis(self):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.add_chat("СИСТЕМА", "Джарвис уже остановлен.", "#8796ad")
            return

        self.stopping = True
        self.add_chat(
            "СИСТЕМА",
            "Запрашиваю остановку. Для корректного выхода main.py "
            "должен поддерживать jarvis_stop.flag.",
            "#ffd479",
        )

        try:
            with open(STOP_FLAG, "w", encoding="utf-8") as file:
                file.write("stop")
        except OSError as exc:
            self.add_chat("ОШИБКА", f"Не удалось создать stop-файл: {exc}", "#ff8585")

        # Даём main.py время завершиться самостоятельно.
        QTimer.singleShot(10000, self.force_stop_if_running)

    def force_stop_if_running(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.add_chat(
                "СИСТЕМА",
                "Процесс не завершился самостоятельно — принудительно останавливаю.",
                "#ffd479",
            )
            self.process.kill()

    def on_finished(self, exit_code, exit_status):
        # Отобразить последнюю строку, если она пришла без перевода строки
        tail = self.output_buffer.strip()
        if tail:
            self.handle_assistant_line(tail)
        self.output_buffer = ""

        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.process_label.setText("Процесс: не запущен")
        self.set_status("ОСТАНОВЛЕН", "statusStopped")
        self.card_voice.value_label.setText("Ожидание")
        self.card_model.value_label.setText("Локальная")

        if self.stopping:
            self.add_chat("СИСТЕМА", "Джарвис остановлен.", "#8796ad")
        else:
            self.add_chat(
                "СИСТЕМА",
                f"Процесс завершён. Код выхода: {exit_code}.",
                "#8796ad",
            )

        self.stopping = False

    def on_process_error(self, error):
        self.add_chat(
            "ОШИБКА",
            f"Ошибка запуска процесса: {self.process.errorString()}",
            "#ff8585",
        )

        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.process_label.setText("Процесс: не запущен")
            self.set_status("ОШИБКА", "statusStopped")

    def open_custom_commands(self):
        dialog = CustomCommandsDialog(self)
        dialog.exec()

    def clear_chat(self):
        self.chat.clear()
        self.message_total = 0
        self.message_count.setText("Сообщений: 0")
        self.add_chat("СИСТЕМА", "История чата очищена.", "#8796ad")

    def closeEvent(self, event):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            try:
                with open(STOP_FLAG, "w", encoding="utf-8") as file:
                    file.write("stop")
            except OSError:
                pass

            self.process.terminate()

            if not self.process.waitForFinished(2000):
                self.process.kill()
                self.process.waitForFinished(1000)

        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))

    window = JarvisGUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

