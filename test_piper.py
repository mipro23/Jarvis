
import wave
import sounddevice as sd
from piper import PiperVoice

MODEL = r"C:\Jarvis\ru_RU-irina-medium.onnx"

print("Загружаю голос...")
voice = PiperVoice.load(MODEL)

with wave.open("test_voice.wav", "wb") as wav_file:
    voice.synthesize_wav(
        "Здравствуйте. Я Джарвис, ваш локальный помощник. "
        "Система готова к работе.",
        wav_file,
    )

with wave.open("test_voice.wav", "rb") as wav_file:
    import numpy as np

    sample_rate = wav_file.getframerate()
    channels = wav_file.getnchannels()
    audio = np.frombuffer(
        wav_file.readframes(wav_file.getnframes()),
        dtype=np.int16,
    ).copy()

audio = audio.reshape(-1, channels)
print("Воспроизвожу тест...")
sd.play(audio, sample_rate)
sd.wait()
print("Готово.")
