"""Единый модуль настроек Джарвиса.

Пользовательская конфигурация хранится в %APPDATA%\\Jarvis\\config.json и не
зависит от текущей рабочей папки. main.py и gui.py работают с настройками
только через этот модуль: загрузка — load_config(), проверка —
validate_config(), изменение и безопасное сохранение — save_config().

Модуль импортирует только стандартную библиотеку, чтобы его могли использовать
и голосовой процесс, и GUI без циклических зависимостей.
"""

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

APP_NAME = "Джарвис"

# Папка программы: относительно неё ищутся файлы моделей по умолчанию.
APP_DIR = Path(__file__).resolve().parent

DEFAULTS = {
    "assistant_name": "Джарвис",
    "mic_device": None,                      # None — микрофон Windows по умолчанию
    "wake_word": "джарвис",                  # можно несколько слов через запятую
    "voice_model": "ru_RU-irina-medium.onnx",
    "ollama_model": "qwen2.5:7b",
    # Облачный ИИ (OpenAI-совместимый API)
    "cloud_enabled": False,
    "base_url": "https://api.groq.com/openai/v1",
    "model": "",
    "api_key": "",
    "max_tokens": 700,
    "timeout_seconds": 35,
}

_INT_KEYS = {"max_tokens", "timeout_seconds"}
_STR_KEYS = {
    "assistant_name", "wake_word", "voice_model", "ollama_model",
    "base_url", "model", "api_key",
}

# Результат последней загрузки: None или описание проблемы с файлом настроек.
_last_problem = None



def get_config_dir():
    import os
    from pathlib import Path

    appdata = os.environ.get("APPDATA")

    if appdata:
        return Path(appdata) / "Jarvis"

    userprofile = os.environ.get("USERPROFILE")

    if userprofile:
        return Path(userprofile) / "AppData" / "Roaming" / "Jarvis"

    return Path("C:/Jarvis/config")



def get_config_path():
    return get_config_dir() / "config.json"


def _coerce(key, value):
    """Приводит известные параметры к ожидаемому типу; неверные — к значению по умолчанию."""
    if key == "mic_device":
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if key in _INT_KEYS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return DEFAULTS[key]
    if key == "cloud_enabled":
        return bool(value)
    if key in _STR_KEYS:
        return value if isinstance(value, str) else DEFAULTS[key]
    return value


def _read_raw():
    """Читает файл настроек. Возвращает (data, error); error=None при успехе."""
    path = get_config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, None
    except OSError as error:
        return {}, error
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return {}, error
    if not isinstance(data, dict):
        return {}, ValueError("корневой элемент JSON — не объект")
    return data, None


def load_config():
    """Загружает настройки: значения по умолчанию + пользовательский файл.

    Отсутствующий файл даёт просто значения по умолчанию. Проблемы с файлом
    фиксируются в config_problem() и не приводят к перезаписи файла здесь.
    """
    global _last_problem
    data, error = _read_raw()
    if error is None:
        _last_problem = None
    elif isinstance(error, OSError):
        _last_problem = (
            f"Не удалось прочитать файл настроек {get_config_path()}: {error}. "
            "Работаю на значениях по умолчанию."
        )
    else:
        _last_problem = (
            f"Файл настроек {get_config_path()} повреждён ({error}). "
            "Работаю на значениях по умолчанию; файл не перезаписывается, "
            "при следующем сохранении будет создана резервная копия."
        )

    cfg = dict(DEFAULTS)
    for key, value in data.items():
        cfg[key] = _coerce(key, value)
    return cfg


def config_problem():
    """Описание проблемы последней загрузки настроек или None."""
    return _last_problem


def save_config(updates):
    """Безопасно меняет настройки: читает файл, сливает updates, пишет атомарно.

    Возвращает (новый полный конфиг, путь резервной копии или None). Ключи,
    которых нет в updates, не теряются — включая неизвестные пользовательские
    параметры и секреты облачного API. Повреждённый файл предварительно
    копируется в config.json.corrupt-<дата-время>, чтобы перезапись не была
    бесшумной.
    """
    path = get_config_path()
    data, error = _read_raw()

    backup_path = None
    if error is not None and path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = path.with_name(f"config.json.corrupt-{stamp}")
        try:
            shutil.copy2(path, backup_path)
        except OSError:
            backup_path = None

    merged = dict(DEFAULTS)
    merged.update(data)
    merged.update(updates)

    get_config_dir().mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)

    global _last_problem
    _last_problem = None
    return merged, backup_path


def resolve_voice_model(cfg=None):
    """Возвращает (путь к голосовой модели, сообщение об ошибке или None).

    Относительное имя ищется рядом с программой и в папке настроек, поэтому
    конфиг не зависит от конкретной машины. Абсолютный путь используется как есть.
    """
    cfg = cfg if cfg is not None else load_config()
    value = str(cfg.get("voice_model") or DEFAULTS["voice_model"]).strip()
    if not value:
        value = DEFAULTS["voice_model"]

    model_path = Path(value)
    if model_path.is_absolute():
        candidates = [model_path]
    else:
        candidates = [APP_DIR / model_path, get_config_dir() / model_path]

    for candidate in candidates:
        if candidate.is_file():
            return candidate, None

    searched = "\n  ".join(str(c) for c in candidates)
    return None, (
        f"Голосовая модель не найдена: «{value}».\n"
        f"  Поиск выполнялся в:\n  {searched}\n"
        f"  Укажи существующий файл в параметре voice_model файла {get_config_path()}."
    )


def get_wake_words(cfg=None):
    """Список слов пробуждения из настроек (регистр и «е/ё» не важны)."""
    cfg = cfg if cfg is not None else load_config()
    raw = str(cfg.get("wake_word") or DEFAULTS["wake_word"]).lower().replace("ё", "е")
    words = [w for w in re.split(r"[,\s]+", raw) if w]
    return words or [DEFAULTS["wake_word"]]


def select_microphone(cfg, devices):
    """Выбирает сохранённый микрофон из списка устройств Windows.

    devices — список описаний входных устройств (sounddevice.query_devices()).
    Возвращает (индекс или None, предупреждение или None). Если сохранённый
    микрофон отсутствует, выдуманный индекс не подставляется: используем
    системный microphone по умолчанию и сообщаем доступные варианты.
    """
    value = cfg.get("mic_device")
    inputs = [d for d in devices if d.get("max_input_channels", 0) > 0]
    if value is None:
        return None, None

    if any(d.get("index") == value for d in inputs):
        return value, None

    listing = "\n".join(f'  [{d["index"]}] {d["name"]}' for d in inputs)
    return None, (
        f"Микрофон №{value} из настроек не найден на этой машине.\n"
        f"Доступные микрофоны:\n{listing}\n"
        f"Выбери нужный номер в настройках GUI или в параметре mic_device "
        f"файла {get_config_path()}.\n"
        "Пока использую микрофон по умолчанию."
    )


def list_input_devices():
    """Список входных устройств для выбора в настройках GUI."""
    try:
        import sounddevice
        devices = sounddevice.query_devices()
    except Exception:
        return []
    return [dict(d) for d in devices if d.get("max_input_channels", 0) > 0]


def validate_config(cfg):
    """Базовые проверки настроек; возвращает список предупреждений."""
    warnings = []

    if not str(cfg.get("wake_word") or "").strip():
        warnings.append("Не задано слово пробуждения (wake_word).")
    if not str(cfg.get("ollama_model") or "").strip():
        warnings.append("Не задана локальная модель Ollama (ollama_model).")

    try:
        max_tokens = int(cfg.get("max_tokens", 0))
        if not 1 <= max_tokens <= 100000:
            warnings.append(f"Подозрительное значение max_tokens: {max_tokens}.")
    except (TypeError, ValueError):
        warnings.append("max_tokens должен быть числом.")

    if cfg.get("cloud_enabled"):
        missing = [
            name for name, key in (
                ("API endpoint", "base_url"),
                ("модель", "model"),
                ("API-ключ", "api_key"),
            )
            if not str(cfg.get(key) or "").strip()
        ]
        if missing:
            warnings.append(
                "Облачный режим включён, но не заполнено: " + ", ".join(missing) + "."
            )

    return warnings
