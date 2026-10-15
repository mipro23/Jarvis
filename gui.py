
import sys
import os
import json
from datetime import datetime

import config
from PySide6.QtCore import Qt, QProcess, QTimer, QThread, Signal
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
    QCheckBox,
    QFormLayout,
    QMessageBox,
    QSystemTrayIcon,
    QStyle,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_FILE = os.path.join(BASE_DIR, "main.py")
PYTHON_EXE = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
STOP_FLAG = os.path.join(BASE_DIR, "jarvis_stop.flag")
CUSTOM_COMMANDS_FILE = os.path.join(BASE_DIR, "custom_commands.json")
TEXT_COMMAND_DIR = os.path.join(BASE_DIR, "jarvis_text_commands")


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
            "Приложение: введи название или полный путь к .exe (например notepad, "
            "Spotify или C:\\Program Files\\App\\app.exe). "
            "Сайт: введи полный адрес, например https://youtube.com. "
            "Для сочетаний клавиш используй разрешённые варианты; для действий без параметра поле не нужно."
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
        action_labels = {value: label for label, value in self.ACTIONS}
        for item in self.commands:
            phrase = item.get("phrase", "")
            action = action_labels.get(item.get("action", ""), item.get("action", ""))
            target = str(item.get("target", "")).strip()
            summary = f"{phrase}  →  {action}"
            if target:
                summary += f" ({target})"
            self.list_widget.addItem(summary)
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
            "open_app": "Название приложения или полный путь к .exe",
            "open_site": "https://example.com",
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
        if action == "open_site" and not (target.lower().startswith("https://") or target.lower().startswith("http://")):
            target = "https://" + target
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



class ApiTestWorker(QThread):
    finished_text = Signal(bool, str)

    def __init__(self, base_url, api_key, model, parent=None):
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def run(self):
        import json
        import urllib.request
        import urllib.error
        endpoint = self.base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Ответь одним словом: работает"}],
            "max_tokens": 20,
            "temperature": 0,
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
            answer = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            self.finished_text.emit(True, "Подключение работает. Ответ: " + str(answer)[:160])
        except Exception as exc:
            self.finished_text.emit(False, f"Не удалось подключиться: {exc}")


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки Джарвиса")
        self.setMinimumWidth(560)
        self.worker = None
        current = config.load_config()

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Микрофон и параметры OpenAI-совместимого API. "
            "Локальные команды Windows и Ollama останутся доступными."
        )
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        layout.addWidget(intro)

        identity_form = QFormLayout()
        self.assistant_name = QLineEdit(str(current.get("assistant_name", "Джарвис")))
        self.assistant_name.setPlaceholderText("Например: Нексус")
        self.wake_word = QLineEdit(str(current.get("wake_word", "джарвис")))
        self.wake_word.setPlaceholderText("Слова через запятую, например: нексус, помощник")
        self.volume = QComboBox()
        self.volume.addItems(["25", "40", "55", "70", "85", "100"])
        self.volume.setCurrentText(str(current.get("voice_volume", 85)))
        identity_form.addRow("Имя ассистента:", self.assistant_name)
        identity_form.addRow("Слово пробуждения:", self.wake_word)
        identity_form.addRow("Громкость голоса (%):", self.volume)
        layout.addLayout(identity_form)

        mic_form = QFormLayout()
        devices = config.list_input_devices()
        self.mic_device = QComboBox()
        self.mic_device.addItem("По умолчанию (системный)", None)
        for device in devices:
            self.mic_device.addItem(
                f'[{device["index"]}] {device["name"]}', device["index"]
            )
        saved_mic = current.get("mic_device")
        position = self.mic_device.findData(saved_mic)
        if saved_mic is not None and position < 0:
            # Сохранённого микрофона нет в системе — предупреждаем,
            # а не подставляем случайное устройство.
            self.mic_device.setItemText(
                0, "По умолчанию (сохранённый микрофон не найден)"
            )
            position = 0
        self.mic_device.setCurrentIndex(position if position >= 0 else 0)
        mic_form.addRow("Микрофон:", self.mic_device)
        layout.addLayout(mic_form)

        self.enabled = QCheckBox("Использовать облачный ИИ для сложных вопросов")
        self.enabled.setChecked(bool(current.get("cloud_enabled", False)))
        layout.addWidget(self.enabled)

        form = QFormLayout()
        self.base_url = QLineEdit(current.get("base_url", "https://api.groq.com/openai/v1"))
        self.base_url.setPlaceholderText("https://api.groq.com/openai/v1")
        self.model = QLineEdit(current.get("model", ""))
        self.model.setPlaceholderText("Название модели у провайдера")
        self.api_key = QLineEdit(current.get("api_key", ""))
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Вставь API-ключ")
        self.api_key.setClearButtonEnabled(True)
        self.max_tokens = QComboBox()
        self.max_tokens.addItems(["300", "500", "700", "1000", "1500"])
        self.max_tokens.setCurrentText(str(current.get("max_tokens", 700)))
        form.addRow("API endpoint:", self.base_url)
        form.addRow("Модель:", self.model)
        form.addRow("API-ключ:", self.api_key)
        form.addRow("Максимум токенов ответа:", self.max_tokens)
        layout.addLayout(form)

        note = QLabel(
            "Пример для Groq: https://api.groq.com/openai/v1\n"
            f"Ключ хранится в локальном файле настроек Windows ({config.get_config_path()}). "
            "Не делись этим файлом и не добавляй его в Git."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.test_button = QPushButton("Проверить API")
        self.test_button.clicked.connect(self.test_api)
        self.save_button = QPushButton("Сохранить")
        self.save_button.clicked.connect(self.save)
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.test_button)
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)

    def settings_data(self):
        return {
            "assistant_name": self.assistant_name.text().strip() or "Джарвис",
            "wake_word": self.wake_word.text().strip() or self.assistant_name.text().strip() or "джарвис",
            "voice_volume": int(self.volume.currentText()),
            "mic_device": self.mic_device.currentData(),
            "cloud_enabled": self.enabled.isChecked(),
            "base_url": self.base_url.text().strip().rstrip("/"),
            "model": self.model.text().strip(),
            "api_key": self.api_key.text().strip(),
            "max_tokens": int(self.max_tokens.currentText()),
        }

    def save(self):
        data = self.settings_data()
        if data["cloud_enabled"] and not all(
            (data["base_url"], data["model"], data["api_key"])
        ):
            QMessageBox.warning(
                self, "Не заполнены настройки",
                "Для облачного режима укажи endpoint, модель и API-ключ. "
                "Либо отключи облачный режим."
            )
            return
        try:
            # save_config сливает значения с существующим файлом, поэтому
            # остальные параметры (слово пробуждения, модель и т.д.) не теряются.
            _, backup_path = config.save_config(data)
        except OSError as exc:
            QMessageBox.critical(self, "Ошибка сохранения", str(exc))
            return
        if backup_path:
            QMessageBox.information(
                self, "Файл настроек был повреждён",
                "Прежний файл настроек не удалось прочитать, поэтому он сохранён "
                f"как резервная копия:\n{backup_path}"
            )
        self.accept()

    def test_api(self):
        data = self.settings_data()
        if not all((data["base_url"], data["model"], data["api_key"])):
            QMessageBox.warning(
                self, "Не заполнены настройки",
                "Укажи endpoint, модель и API-ключ."
            )
            return
        self.test_button.setEnabled(False)
        self.status.setText("Проверяю подключение…")
        self.worker = ApiTestWorker(
            data["base_url"], data["api_key"], data["model"], self
        )
        self.worker.finished_text.connect(self.on_test_finished)
        self.worker.start()

    def on_test_finished(self, success, message):
        self.test_button.setEnabled(True)
        self.status.setText(message)
        self.status.setStyleSheet(
            "color: #73efb1;" if success else "color: #ff8585;"
        )


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
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        self.tray_icon.setToolTip("JARVIS")
        self.tray_icon.show()

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

        self.settings_button = QPushButton("⚙  Настройки")
        self.settings_button.clicked.connect(self.open_settings)
        side.addWidget(self.settings_button)

        self.commands_button = QPushButton("☷  Мои команды")
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

        # Текстовый ввод команды: main.py забирает его из файловой очереди
        input_row = QHBoxLayout()
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText(
            "Напиши команду текстом — Джарвис выполнит её без слова пробуждения"
        )
        self.text_input.returnPressed.connect(self.send_text_command)
        self.send_button = QPushButton("Отправить")
        self.send_button.clicked.connect(self.send_text_command)
        input_row.addWidget(self.text_input, 1)
        input_row.addWidget(self.send_button)
        chat_layout.addLayout(input_row)

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

        env = self.process.processEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        env.insert("HF_HUB_VERBOSITY", "error")

        # Передаём дочернему main.py корректные пути пользователя.
        # Некоторые Windows-сборки Python не определяют Path.home() сами.
        userprofile = os.environ.get("USERPROFILE") or r"C:\\Users\\home"
        appdata = os.environ.get("APPDATA") or os.path.join(
            userprofile, "AppData", "Roaming"
        )
        localappdata = os.environ.get("LOCALAPPDATA") or os.path.join(
            userprofile, "AppData", "Local"
        )
        env.insert("USERPROFILE", userprofile)
        env.insert("HOME", userprofile)
        env.insert("APPDATA", appdata)
        env.insert("LOCALAPPDATA", localappdata)

        # Не позволяем Hugging Face выбирать кэш через Path.home().
        hf_home = os.path.join(BASE_DIR, "cache", "huggingface")
        hf_hub_cache = os.path.join(hf_home, "hub")
        os.makedirs(hf_hub_cache, exist_ok=True)
        env.insert("HF_HOME", hf_home)
        env.insert("HF_HUB_CACHE", hf_hub_cache)

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
            self.set_status("ГОТОВ", "statusReady")
            self.card_voice.value_label.setText("Ожидание команды")
            self.card_model.value_label.setText("Загружена")
            self.add_chat("СИСТЕМА", line, "#73efb1")
            return

        if lower.startswith(("пробуждение:", "wake detected:")):
            name = line.split(":", 1)[-1].strip() or config.load_config().get("assistant_name", "Ассистент")
            self.card_voice.value_label.setText("Активирован")
            self.add_chat("🔔 АССИСТЕНТ СЛУШАЕТ", f"{name} услышал тебя. Говори команду.", "#73efb1")
            try:
                if hasattr(self, "tray_icon") and self.tray_icon.isVisible():
                    self.tray_icon.showMessage(
                        "Ассистент слушает",
                        f"{name} услышал тебя. Говори команду.",
                        self.tray_icon.MessageIcon.Information,
                        4000,
                    )
            except Exception:
                pass
            return

        # Текст распознанной речи
        if lower.startswith(("слышу:", "услышала:", "wake:", "wake word:")):
            self.card_voice.value_label.setText("Слушает")
            self.add_chat("🎙️ ДЖАРВИС УСЛЫШАЛ", line.split(":", 1)[-1], "#67d8ff")
            return

        if lower.startswith(("ты:", "ты (текст):", "пользователь:", "распознано:")):
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

    def send_text_command(self):
        text = self.text_input.text().strip()
        if not text:
            return
        self.text_input.clear()

        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.add_chat(
                "СИСТЕМА",
                "Джарвис не запущен. Нажми «Запустить Джарвиса».",
                "#ffd479",
            )
            return

        try:
            os.makedirs(TEXT_COMMAND_DIR, exist_ok=True)
            filename = "{:%Y%m%d-%H%M%S}-{}.txt".format(
                datetime.now(), os.urandom(4).hex()
            )
            with open(os.path.join(TEXT_COMMAND_DIR, filename), "w", encoding="utf-8") as file:
                file.write(text)
        except OSError as exc:
            self.add_chat("ОШИБКА", f"Не удалось передать команду: {exc}", "#ff8585")
            return

        self.add_chat("🧑 ТЫ (текст)", text, "#d8a5ff")

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
        # Редактор сохраняет команды в custom_commands.json, который читает main.py.
        self.commands_dialog = CustomCommandsDialog(self)
        self.commands_dialog.setWindowTitle("Мои команды Джарвиса")
        self.commands_dialog.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinMaxButtonsHint
        )
        self.commands_dialog.setModal(False)
        self.commands_dialog.setMinimumSize(620, 560)
        self.commands_dialog.setStyleSheet("""
            QWidget { background-color: #0b1020; color: #e8eefc; }
            QLabel#muted { color: #8291ad; }
            QLineEdit, QComboBox, QListWidget {
                background-color: #0d1425; color: #e8eefc;
                border: 1px solid #2a3a5b; border-radius: 6px; padding: 7px;
            }
            QPushButton { background-color: #1b2740; border: 1px solid #2a3a5b;
                border-radius: 8px; padding: 9px; color: #e8eefc; font-weight: 600; }
            QPushButton:hover { background-color: #263856; border-color: #67d8ff; }
        """)
        # Показываем отдельное окно, а не дочерний виджет в левом верхнем углу.
        self.commands_dialog.adjustSize()
        self.commands_dialog.show()
        self.commands_dialog.raise_()
        self.commands_dialog.activateWindow()
        parent_frame = self.frameGeometry()
        dialog_frame = self.commands_dialog.frameGeometry()
        dialog_frame.moveCenter(parent_frame.center())
        self.commands_dialog.move(dialog_frame.topLeft())

    def open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.add_chat(
                "СИСТЕМА",
                "Настройки сохранены. Микрофон и слово пробуждения применятся "
                "при следующем запуске, облачный ИИ — при следующем запросе.",
                "#73efb1",
            )
            self.card_model.value_label.setText(
                "Гибридная" if dialog.settings_data()["cloud_enabled"] else "Локальная"
            )

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

