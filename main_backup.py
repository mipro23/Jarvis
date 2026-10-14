
import json
import re
import time
import wave
import webbrowser
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pyautogui
import sounddevice as sd
from faster_whisper import WhisperModel
from ollama import chat
from piper import PiperVoice


# ---------------- НАСТРОЙКИ ----------------

MODEL = "qwen2.5:7b"
VOICE_MODEL = r"C:\Jarvis\ru_RU-irina-medium.onnx"

SAMPLE_RATE = 16000
RECORD_SECONDS = 5
MIC_DEVICE = 1

SYSTEM = """
Ты Джарвис, локальный голосовой помощник Windows 11.
Всегда отвечай на русском языке, кратко и дружелюбно.
Ты не Алиса и не другой голосовой помощник.

Если пользователь просит открыть приложение, сайт или управлять
окнами, определи подходящее действие из списка:
open_app, open_site, minimize_window, maximize_window,
restore_window, switch_window, close_window, none.

Возвращай только один JSON-объект без Markdown:
{"action":"none","target":"","reply":"Твой ответ"}

Допустимые приложения: notepad, calculator, explorer, browser.
Для сайтов target должен быть одним из:
google, youtube, wikipedia.
Не предлагай другие действия. Не выдумывай результат выполнения.
Если команда неясна, используй action none и попроси уточнение.
"""


# ---------------- БЕЗОПАСНЫЙ СПИСОК ----------------

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

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.2


# ---------------- РЕЧЬ ----------------

def listen(whisper):
    print(f"\nГовори сейчас ({RECORD_SECONDS} секунд)...")
    audio = sd.rec(
        int(SAMPLE_RATE * RECORD_SECONDS),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=MIC_DEVICE,
    )
    sd.wait()

    segments, _ = whisper.transcribe(
        audio.flatten(),
        language="ru",
        vad_filter=True,
    )
    text = " ".join(s.text.strip() for s in segments).strip()
    print("Ты:", text)
    return text


def speak(voice, text):
    if not text:
        return

    # Используем временный WAV в папке проекта
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


# ---------------- ВЫПОЛНЕНИЕ КОМАНД ----------------

def execute_action(action, target):
    """Выполняет только явно разрешённые действия."""

    if action == "open_app":
        if target not in APPS:
            return "Это приложение не входит в список разрешённых."

        if target == "browser":
            webbrowser.open("https://www.google.com/")
            return "Открываю браузер."

        try:
            subprocess.Popen(APPS[target], shell=False)
            return "Запускаю приложение."
        except Exception as error:
            return f"Не удалось запустить приложение: {error}"

    if action == "open_site":
        if target not in SITES:
            return "Этот сайт не входит в список разрешённых."

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
        return "Закрытие окна отключено в этой версии. Закрой его вручную или добавим подтверждение."

    return None


def parse_model_response(content):
    """Извлекает JSON, не выполняя код из ответа модели."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(data, dict):
        return None

    action = data.get("action", "none")
    target = data.get("target", "")
    reply = data.get("reply", "")

    if not all(isinstance(x, str) for x in (action, target, reply)):
        return None

    allowed_actions = {
        "open_app", "open_site", "minimize_window",
        "maximize_window", "restore_window",
        "switch_window", "close_window", "none",
    }
    if action not in allowed_actions:
        return None

    return {
        "action": action,
        "target": target.lower().strip(),
        "reply": reply.strip(),
    }


# ---------------- ЗАПУСК ----------------

def main():
    print("=" * 45)
    print("Загружаю локальный голос Piper...")
    voice = PiperVoice.load(VOICE_MODEL)

    print("Загружаю распознавание речи...")
    whisper = WhisperModel("base", device="cpu", compute_type="int8")

    print("Джарвис готов!")
    print("Enter — говорить | q — выход")

    while True:
        try:
            key = input("\nEnter — команда | q — выход: ").strip().lower()

            if key == "q":
                speak(voice, "До связи!")
                break

            text = listen(whisper)
            if not text:
                print("Речь не распознана.")
                continue

            if text.lower() in ("выход", "остановись", "завершить работу"):
                speak(voice, "До связи!")
                break

            result = chat(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": text},
                ],
                format="json",
                options={"temperature": 0},
            )

            command = parse_model_response(result.message.content)

            if not command:
                answer = "Не удалось понять ответ модели. Повтори команду."
                print("JARVIS:", answer)
                speak(voice, answer)
                continue

            action = command["action"]
            target = command["target"]

            if action != "none":
                print(f"Команда: {action}, объект: {target}")

                # Не разрешаем модели подменять аргументы произвольным текстом.
                if action == "open_app" and target not in APPS:
                    answer = "Я могу открыть Блокнот, Калькулятор, Проводник или браузер."
                elif action == "open_site" and target not in SITES:
                    answer = "Пока доступны Google, YouTube и Википедия."
                else:
                    answer = execute_action(action, target) or command["reply"]
            else:
                answer = command["reply"] or "Чем могу помочь?"

            print("\nJARVIS:", answer)
            speak(voice, answer)

        except KeyboardInterrupt:
            print("\nДжарвис остановлен.")
            break
        except Exception as error:
            print("Ошибка:", error)


if __name__ == "__main__":
    main()
