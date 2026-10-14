import sounddevice as sd
import soundfile as sf

device = 1
seconds = 5
rate = 16000

print("Говори в микрофон 5 секунд...")
audio = sd.rec(
    int(seconds * rate),
    samplerate=rate,
    channels=1,
    dtype="float32",
    device=device
)
sd.wait()

sf.write("mic_test.wav", audio, rate)
print("Запись сохранена в C:\\Jarvis\\mic_test.wav")
