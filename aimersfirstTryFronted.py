import math
import threading
import time
import numpy as np
import pyaudio
import flet as ft

# --- Audio Backend (Professional DSP) ---
SAMPLE_RATE = 44100
BUFFER_SIZE = 4096
GUITAR_STRINGS = {
    "E2": 82.41,
    "A2": 110.00,
    "D3": 146.83,
    "G3": 196.00,
    "B3": 246.94,
    "E4": 329.63
}
ORDERED_KEYS = ["E2", "A2", "D3", "G3", "B3", "E4"]
NOISE_THRESHOLD = 0.02

class AudioBackend:
    def __init__(self, callback_func):
        self.pa = pyaudio.PyAudio()
        self.stream = None
        self.running = False
        self.callback_func = callback_func
        self.manual_target = None

    def start(self):
        self.running = True
        try:
            self.stream = self.pa.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=BUFFER_SIZE
            )
            self.thread = threading.Thread(target=self._process_loop, daemon=True)
            self.thread.start()
        except Exception as e:
            print(f"Error starting audio stream: {e}")

    def stop(self):
        self.running = False
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass
        self.pa.terminate()

    def set_manual_target(self, note_name):
        if note_name == "Auto":
            self.manual_target = None
        else:
            self.manual_target = GUITAR_STRINGS[note_name]

    def _process_loop(self):
        window = np.hanning(BUFFER_SIZE)
        
        while self.running:
            try:
                if self.stream is None or not self.stream.is_active():
                    time.sleep(0.1)
                    continue

                data = self.stream.read(BUFFER_SIZE, exception_on_overflow=False)
                samples = np.frombuffer(data, dtype=np.float32)

                # 1. Volume Gate
                volume = np.sqrt(np.mean(samples**2))
                if volume < NOISE_THRESHOLD:
                    self.callback_func(0, 0, "Silence", False)
                    continue

                # 2. Pitch Detection
                corr = np.correlate(samples * window, samples * window, mode='full')
                corr = corr[len(corr)//2:]
                
                d = np.diff(corr)
                try:
                    start = np.where(d > 0)[0][0]
                    peak = np.argmax(corr[start:]) + start
                except IndexError:
                    continue

                if 0 < peak < len(corr) - 1:
                    alpha = corr[peak - 1]
                    beta = corr[peak]
                    gamma = corr[peak + 1]
                    peak_refined = peak + (alpha - gamma) / (2 * (alpha - 2 * beta + gamma))
                else:
                    peak_refined = peak

                freq = SAMPLE_RATE / peak_refined

                if freq < 60 or freq > 500:
                    continue

                # 3. Determine Target
                target_freq = 0
                closest_note_name = ""
                
                if self.manual_target:
                    target_freq = self.manual_target
                    for name, f in GUITAR_STRINGS.items():
                        if f == target_freq:
                            closest_note_name = name
                else:
                    min_dist = float('inf')
                    for name, f_target in GUITAR_STRINGS.items():
                        dist = abs(f_target - freq)
                        if dist < min_dist:
                            min_dist = dist
                            target_freq = f_target
                            closest_note_name = name

                try:
                    cents = 1200 * math.log2(freq / target_freq)
                except ValueError:
                    cents = 0

                self.callback_func(freq, cents, closest_note_name, True)
                time.sleep(0.05)

            except Exception as e:
                # print(f"Audio processing error: {e}")
                pass

# --- Modern UI (Flet) ---
def main(page: ft.Page):
    page.title = "Pro Guitar Tuner"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window_width = 400
    page.window_height = 600
    page.theme_mode = ft.ThemeMode.DARK

    # UI Elements using ft.Colors (Capitalized)
    note_text = ft.Text(value="--", size=80, weight=ft.FontWeight.BOLD)
    freq_text = ft.Text(value="0.0 Hz", size=20, color=ft.Colors.GREY)
    guide_text = ft.Text(value="Pluck a string", size=18, weight=ft.FontWeight.W_500)
    
    # Progress Bar (0.5 is perfectly tuned)
    bar = ft.ProgressBar(width=300, value=0.5, color=ft.Colors.BLUE, bgcolor=ft.Colors.GREY_800)

    def on_mode_change(e):
        audio.set_manual_target(mode_dropdown.value)

    mode_dropdown = ft.Dropdown(
        width=150,
        label="Mode",
        options=[ft.dropdown.Option("Auto")] + [ft.dropdown.Option(k) for k in ORDERED_KEYS],
        value="Auto",
        on_change=on_mode_change
    )

    layout = ft.Column(
        [
            mode_dropdown,
            ft.Container(height=20),
            note_text,
            freq_text,
            ft.Container(height=20),
            bar,
            ft.Container(height=10),
            guide_text,
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )
    
    page.add(layout)

    def update_ui(freq, cents, note_name, is_active):
        if not is_active:
            note_text.value = "--"
            freq_text.value = "Silence"
            bar.value = 0.5
            bar.color = ft.Colors.BLUE
            guide_text.value = "Pluck a string"
            guide_text.color = ft.Colors.WHITE
            page.update()
            return

        note_text.value = note_name
        freq_text.value = f"{freq:.1f} Hz"
        
        # Map cents (-50 to +50) to Progress Bar (0.0 to 1.0)
        normalized_val = (cents + 50) / 100
        normalized_val = max(0.0, min(1.0, normalized_val))
        bar.value = normalized_val

        # Color Logic
        if abs(cents) < 5:
            bar.color = ft.Colors.GREEN
            guide_text.value = "PERFECT"
            guide_text.color = ft.Colors.GREEN
        elif cents < 0:
            bar.color = ft.Colors.ORANGE
            guide_text.value = "Too Flat (Tune Up)"
            guide_text.color = ft.Colors.ORANGE
        else:
            bar.color = ft.Colors.RED
            guide_text.value = "Too Sharp (Tune Down)"
            guide_text.color = ft.Colors.RED
        
        page.update()

    audio = AudioBackend(update_ui)
    audio.start()

    def window_event(e):
        if e.data == "close":
            audio.stop()
            page.window_destroy()

    page.window_prevent_close = True
    page.on_window_event = window_event

if __name__ == "__main__":
    ft.app(target=main)