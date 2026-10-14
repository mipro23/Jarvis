import mss
from PIL import Image
import json
import re
import time
import wave
import subprocess
import webbrowser
from pathlib import Path

import numpy as np
import sounddevice as sd
import pyautogui
from pathlib import Path

STOP_FLAG = Path(__file__).parent / "jarvis_stop.flag"


def stop_requested():
    return STOP_FLAG.exists()

from faster_whisper import WhisperModel
from ollama import chat
from piper import PiperVoice


# ============== НАСТРОЙКИ ==============

MODEL = "qwen2.5:7b"
VOICE_MODEL = r"C:\Jarvis\ru_RU-irina-medium.onnx"

SAMPLE_RATE = 16000
MIC_DEVICE = 1

# Частота проверки ключевого слова и длительность команды
WAKE_CHUNK_SECONDS = 2

SAMPLE_RATE = 16000

# Сколько тишины означает, что фраза закончилась
END_SILENCE_SECONDS = 0.8

# Максимальное время ожидания команды
MAX_COMMAND_SECONDS = 12

# Минимальная длительность речи, чтобы не принять шум за команду
MIN_SPEECH_SECONDS = 0.25

# Начальный запас аудио, чтобы не обрезать первые слова
PRE_ROLL_SECONDS = 0.3

# Минимальная громкость речи; при необходимости настроим
SPEECH_THRESHOLD = 0.012


WAKE_WORDS = (
    "алиска",
    "алис",
    "алиса",
)

SYSTEM = """
Ты Джарвис — локальный голосовой помощник Windows 11.
Всегда отвечай на русском языке, кратко и дружелюбно.

Для команд управления компьютером возвращай JSON:
{"action":"none","target":"","reply":"Ответ пользователю"}

Допустимые действия:
open_app, open_site, minimize_window, maximize_window,
restore_window, switch_window, close_window, none.

Приложения: notepad, calculator, explorer, browser.
Сайты: google, youtube, wikipedia.
Для окон target оставляй пустым.
Не выдумывай результат выполнения.
Не возвращай код или команды оболочки.
"""

APPS = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "browser": None,
}

SITES = {
    "google": "https://www.google.com/",
    "youtube": "https://www.youtube.com/",
    "wikipedia": "https://ru.wikipedia.org/",
}

CUSTOM_COMMANDS_FILE = Path(__file__).parent / "custom_commands.json"


def normalize_phrase(text):
    text = text.lower().replace("ё", "е")
    return " ".join(re.sub(r"[^\w\s+]+", " ", text).split())


def load_custom_commands():
    try:
        with open(CUSTOM_COMMANDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def run_custom_command(command, voice):
    action = command.get("action", "")
    target = str(command.get("target", "")).strip()
    target_key = target.lower().strip()

    if action == "open_app":
        if target_key not in APPS:
            return "Для этой команды указано неизвестное приложение."
        if target_key == "browser":
            webbrowser.open(SITES["google"])
        else:
            subprocess.Popen(APPS[target_key], shell=False)
        return "Выполняю пользовательскую команду."

    if action == "open_site":
        if target_key not in SITES:
            return "Для этой команды указан неизвестный сайт."
        webbrowser.open(SITES[target_key])
        return "Открываю сайт."

    if action == "hotkey":
        allowed_hotkeys = {
            "ctrl+shift+esc": ("ctrl", "shift", "esc"),
            "win+d": ("win", "d"),
            "win+e": ("win", "e"),
            "win+r": ("win", "r"),
            "ctrl+shift+n": ("ctrl", "shift", "n"),
            "alt+tab": ("alt", "tab"),
        }
        keys = allowed_hotkeys.get(target_key.replace(" ", ""))
        if not keys:
            return "Это сочетание клавиш не разрешено. Измени его в настройках команды."
        pyautogui.hotkey(*keys)
        return "Выполняю сочетание клавиш."

    if action == "say":
        if not target:
            return "Для этой команды не задан текст ответа."
        speak(voice, target)
        return ""

    if action == "minimize_window":
        pyautogui.hotkey("win", "down")
        return "Сворачиваю активное окно."
    if action == "maximize_window":
        pyautogui.hotkey("win", "up")
        return "Разворачиваю активное окно."
    if action == "switch_window":
        pyautogui.hotkey("alt", "tab")
        return "Переключаю окно."
    return "Неизвестное действие пользовательской команды."


def match_custom_command(text):
    normalized = normalize_phrase(text)
    if not normalized:
        return None
    # Более длинные фразы проверяются первыми, чтобы избежать совпадений по части фразы.
    commands = sorted(load_custom_commands(), key=lambda item: len(str(item.get("phrase", ""))), reverse=True)
    for item in commands:
        phrase = normalize_phrase(str(item.get("phrase", "")))
        if phrase and (normalized == phrase or re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", normalized)):
            return item
    return None

ALLOWED_ACTIONS = {
    "open_app", "open_site", "minimize_window",
    "maximize_window", "restore_window",
    "switch_window", "close_window", "none",
}

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.2


# ============== РАСПОЗНАВАНИЕ ==============

def record_audio(seconds):
    """Записывает один фрагмент с выбранного микрофона."""
    audio = sd.rec(
        int(SAMPLE_RATE * seconds),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=MIC_DEVICE,
    )
    sd.wait()
    return audio.flatten()



def transcribe(whisper, audio):
    segments, _ = whisper.transcribe(
        audio,
        language="ru",
        vad_filter=True,
    )
    text = " ".join(s.text.strip() for s in segments).strip()
    return text





def wait_for_wake_word(whisper):
    """Ожидает имя Алисы и возвращает команду, если она прозвучала сразу."""
    wake_pattern = re.compile(
        r"\\b(?:алиска|алис|алиса)\\b",
        flags=re.IGNORECASE,
    )

    while not stop_requested():
        # Короткие фрагменты уменьшают задержку реакции.
        audio = record_audio(1.5)
        text = transcribe(whisper, audio)

        if not text:
            continue

        print("Слышу:", text, flush=True)
        match = wake_pattern.search(text.lower().replace("ё", "е"))

        if match:
            # Если пользователь сказал «Алиска, открой ...» одним
            # предложением, сразу передаём остаток как команду.
            original_match = wake_pattern.search(text)
            if original_match:
                remainder = text[original_match.end():].strip(" ,.!?:;—-")
            else:
                remainder = ""

            return remainder

    return ""



def listen_for_command(whisper):
    """Записывает речь до обнаружения конца фразы."""
    import time
    from collections import deque

    sample_rate = 16000
    block_seconds = 0.1
    block_size = int(sample_rate * block_seconds)

    end_silence_blocks = max(
        1, int(END_SILENCE_SECONDS / block_seconds)
    )
    pre_roll_blocks = max(
        1, int(PRE_ROLL_SECONDS / block_seconds)
    )

    # Храним последние блоки, включая короткую паузу перед речью
    pre_roll = deque(maxlen=pre_roll_blocks)
    audio_parts = []

    speech_started = False
    silence_blocks = 0
    speech_blocks = 0
    start_time = time.monotonic()

    # Сначала оцениваем фоновый шум
    noise_levels = []

    print("Слушаю команду. Говори после сигнала...")

    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            blocksize=block_size,
            device=MIC_DEVICE,
        ) as stream:

            while True:
                data, overflowed = stream.read(block_size)
                chunk = data[:, 0].copy()

                elapsed = time.monotonic() - start_time
                if elapsed >= MAX_COMMAND_SECONDS:
                    break

                # Первые 0.3 секунды оцениваем фоновый шум
                if elapsed < 0.3:
                    noise_levels.append(
                        float(np.sqrt(np.mean(chunk * chunk)))
                    )
                    pre_roll.append(chunk)
                    continue

                noise_level = (
                    float(np.median(noise_levels))
                    if noise_levels else 0.0
                )
                threshold = max(
                    SPEECH_THRESHOLD,
                    noise_level * 3.0,
                )

                rms = float(np.sqrt(np.mean(chunk * chunk)))
                is_speech = rms >= threshold

                if not speech_started:
                    pre_roll.append(chunk)

                    if is_speech:
                        speech_started = True
                        audio_parts.extend(list(pre_roll))
                        speech_blocks = 1
                        silence_blocks = 0
                        print("Речь обнаружена...")
                    continue

                audio_parts.append(chunk)

                if is_speech:
                    speech_blocks += 1
                    silence_blocks = 0
                else:
                    silence_blocks += 1

                # Завершаем запись, когда речь закончилась
                if (
                    silence_blocks >= end_silence_blocks
                    and speech_blocks * block_seconds
                    >= MIN_SPEECH_SECONDS
                ):
                    break

    except Exception as error:
        print("Ошибка записи команды:", error)
        return ""

    if not speech_started or not audio_parts:
        print("Речь не обнаружена.")
        return ""

    audio = np.concatenate(audio_parts).astype(np.float32)

    print("Распознаю команду...")
    text = transcribe(whisper, audio)

    if text:
        print("Ты:", text, flush=True)
    else:
        print("Не удалось распознать команду.", flush=True)

    return text


# ============== ОЗВУЧИВАНИЕ ==============

def speak(voice, text):
    if not text:
        return

    wav_path = Path(__file__).parent / "jarvis_speech.wav"

    with wave.open(str(wav_path), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)

    with wave.open(str(wav_path), "rb") as wav_file:
        rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        audio = np.frombuffer(
            wav_file.readframes(wav_file.getnframes()),
            dtype=np.int16,
        ).copy()

    audio = audio.reshape(-1, channels).astype(np.float32) / 32768.0
    sd.play(audio, rate)
    sd.wait()

    # Даём микрофону время, чтобы не принять конец озвучивания за команду
    time.sleep(0.5)




VISION_MODEL = "qwen2.5vl:3b"

def look_at_screen(question="Что сейчас видно на экране?"):
    """Делает скриншот и передаёт его локальной модели зрения."""
    screenshot_path = Path(__file__).parent / "jarvis_screen.png"

    try:
        with mss.MSS() as screen:
            # Снимаем основной монитор
            monitor = screen.monitors[1]
            shot = screen.grab(monitor)
            image = Image.frombytes(
                "RGB",
                shot.size,
                shot.rgb,
            )

            # Уменьшаем большое изображение, чтобы снизить нагрузку
            image.thumbnail((1600, 1000))
            image.save(screenshot_path, format="PNG")

        print("Анализирую экран локальной моделью зрения...")

        result = chat(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Ты — зрение локального помощника Алиски. "
                        "Опиши только то, что действительно видно "
                        "на скриншоте. Отвечай по-русски, кратко. "
                        "Не утверждай, что выполнил действия. "
                        "Вопрос пользователя: " + question
                    ),
                    "images": [str(screenshot_path)],
                }
            ],
            options={"temperature": 0},
        )

        return result.message.content.strip()

    except Exception as error:
        print("Ошибка анализа экрана:", error)
        return (
            "Не удалось проанализировать экран. "
            "Проверь, что модель зрения установлена и Ollama запущена."
        )


# ============== БЕЗОПАСНЫЕ ДЕЙСТВИЯ ==============

def execute_action(action, target):
    if action == "open_app":
        if target not in APPS:
            return "Это приложение не входит в список разрешённых."

        if target == "browser":
            webbrowser.open(SITES["google"])
            return "Открываю браузер."

        try:
            subprocess.Popen(APPS[target], shell=False)
            return "Запускаю приложение."
        except Exception as error:
            print("Ошибка запуска приложения:", error)
            return "Не удалось запустить приложение."

    if action == "open_site":
        if target not in SITES:
            return "Пока доступны Google, YouTube и Википедия."

        webbrowser.open(SITES[target])
        return "Открываю сайт."

    if action == "minimize_window":
        pyautogui.hotkey("win", "down")
        return "Сворачиваю активное окно."

    if action == "maximize_window":
        pyautogui.hotkey("win", "up")
        return "Разворачиваю активное окно."

    if action == "restore_window":
        pyautogui.hotkey("win", "shift", "m")
        return "Пробую восстановить свёрнутые окна."

    if action == "switch_window":
        pyautogui.hotkey("alt", "tab")
        return "Переключаю окно."

    if action == "close_window":
        # Без подтверждения окно не закрываем.
        return "Закрытие окон пока отключено ради безопасности."

    return None


def parse_response(content):
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    action = data.get("action", "none")
    target = data.get("target", "")
    reply = data.get("reply", "")

    if not all(isinstance(x, str) for x in (action, target, reply)):
        return None

    if action not in ALLOWED_ACTIONS:
        return None

    return {
        "action": action,
        "target": target.lower().strip(),
        "reply": reply.strip(),
    }


# ============== ОБРАБОТКА КОМАНД ==============

def handle_command(text, voice):
    if not text:
        speak(voice, "Я не расслышал команду. Позови меня ещё раз.")
        return

    custom_command = match_custom_command(text)
    if custom_command:
        try:
            print("Пользовательская команда:", custom_command.get("phrase", ""), flush=True)
            answer = run_custom_command(custom_command, voice)
            if answer:
                print("ДЖАРВИС:", answer, flush=True)
                speak(voice, answer)
        except Exception as error:
            print("Ошибка пользовательской команды:", error, flush=True)
            speak(voice, "Не удалось выполнить пользовательскую команду.")
        return

    # Команды, которые требуют анализа скриншота
    vision_phrases = (
        "что на экране",
        "посмотри на экран",
        "что открыто",
        "что у меня открыто",
        "опиши экран",
        "прочитай экран",
        "что ты видишь",
        "посмотри экран",
    )

    normalized_text = text.lower().replace("ё", "е")

    if any(phrase in normalized_text for phrase in vision_phrases):
        print("Алиска смотрит на экран...")
        answer = look_at_screen(text)
        print("АЛИСКА:", answer, flush=True)
        speak(voice, answer)
        return


    if text.lower().strip() in (
        "выход", "остановись", "завершить работу",
        "джарвис выход", "джарвис остановись",
    ):
        speak(voice, "Чтобы полностью выключить меня, нажми Ctrl и C в окне программы.")
        return

    try:
        result = chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": text},
            ],
            format="json",
            options={"temperature": 0},
        )

        command = parse_response(result.message.content)

        if not command:
            speak(voice, "Не удалось разобрать команду. Попробуй ещё раз.")
            return

        action = command["action"]
        target = command["target"]

        if action == "none":
            answer = command["reply"] or "Слушаю тебя."
        elif action == "open_app" and target not in APPS:
            answer = "Я могу открыть Блокнот, Калькулятор, Проводник или браузер."
        elif action == "open_site" and target not in SITES:
            answer = "Пока доступны Google, YouTube и Википедия."
        else:
            answer = execute_action(action, target) or "Команда не выполнена."

        print("ДЖАРВИС:", answer, flush=True)
        speak(voice, answer)

    except Exception as error:
        print("Ошибка Ollama или команды:", error)
        speak(voice, "Не получилось обработать команду. Попробуй ещё раз.")


# ============== ЗАПУСК ==============

def main():
    print("=" * 45)
    print("Загружаю голос Piper...")
    voice = PiperVoice.load(VOICE_MODEL)

    print("Загружаю Faster-Whisper...")
    whisper = WhisperModel(
        "base",
        device="cpu",
        compute_type="int8",
    )

    print("\\nДЖАРВИС ГОТОВ.", flush=True)
    print("Скажи «Алиска», затем команду — можно без паузы.")
    print("Для полной остановки нажми Ctrl+C.")
    print("Для аварийной остановки автоматизации перемести мышь в верхний левый угол.")

    try:
        while not stop_requested():
            print("\\nОжидаю ключевую фразу...", flush=True)
            command = wait_for_wake_word(whisper)

            if stop_requested():
                break

            # Если команда не прозвучала вместе с именем, начинаем слушать сразу.
            if not command:
                command = listen_for_command(whisper)

            if stop_requested():
                break

            if command:
                handle_command(command, voice)

    except KeyboardInterrupt:
        print("\nЗавершаю работу Джарвиса...")
    finally:
        try:
            sd.stop()
        except Exception:
            pass

        print("Джарвис остановлен.")

if __name__ == "__main__":
    main()
