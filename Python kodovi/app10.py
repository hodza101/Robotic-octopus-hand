import json
import math
import threading
import time
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
import serial
from serial.tools import list_ports

BAUD = 9600
APP_TITLE = "SpiRob Grappler Mission Control"
CONFIG_PATH = Path("grappler_config.json")
LOG_EXPORT_PATH = Path("grappler_log_export.json")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "bg": "#060a13",
    "sidebar": "#090f1c",
    "card": "#111827",
    "card2": "#0b1220",
    "card3": "#152033",
    "blue": "#2563eb",
    "blue2": "#1d4ed8",
    "red": "#ef4444",
    "red2": "#dc2626",
    "amber": "#f59e0b",
    "green": "#22c55e",
    "muted": "#94a3b8",
    "soft": "#cbd5e1",
    "border": "#26364d",
    "disabled": "#334155",
}

SERVO1_HOME = 175
SERVO2_HOME = 5
SERVO1_GRIP = 5
SERVO2_GRIP = 175


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


class RoundIndicator(ctk.CTkFrame):
    def __init__(self, parent, title, value=0, color=COLORS["green"], width=102, height=116):
        super().__init__(parent, fg_color="transparent", width=width, height=height)
        self.pack_propagate(False)
        self.title = title
        self.value = value
        self.color = color
        self.canvas = ctk.CTkCanvas(self, width=width, height=height, bg=COLORS["card"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.draw(value)

    def draw(self, value=None):
        if value is not None:
            self.value = max(0, min(100, int(value)))
        c = self.canvas
        c.delete("all")
        w = int(c["width"])
        h = int(c["height"])
        cx = w // 2
        cy = 48
        r = 34
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#1f2937", width=10)
        extent = -359 * (self.value / 100)
        c.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=extent, style="arc", outline=self.color, width=10)
        c.create_text(cx, cy - 4, text=f"{self.value}%", fill="white", font=("Consolas", 15, "bold"))
        c.create_text(cx, cy + 18, text=self.title, fill=COLORS["muted"], font=("Consolas", 10, "bold"))
        c.create_text(cx, 98, text="ACTIVE" if self.value else "IDLE", fill=self.color if self.value else COLORS["muted"], font=("Consolas", 8, "bold"))


class GrapplerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1500x860")
        self.minsize(1180, 720)
        self.configure(fg_color=COLORS["bg"])

        self.ser = None
        self.reader_alive = False
        self.reader_thread = None
        self.connected = False
        self.last_ack_time = None
        self.logs = []
        self.recording = False
        self.macro = []

        self.s1 = SERVO1_HOME
        self.s2 = SERVO2_HOME
        self.grip = 0
        self.last_command = "Nema"
        self.selected_port = ctk.StringVar(value="-")
        self.live_calibration = ctk.BooleanVar(value=False)
        self.pending_live_job_s1 = None
        self.pending_live_job_s2 = None

        self.load_config()
        self.build_ui()
        self.refresh_ports()
        self.after(300, self.draw_twin)
        self.after(1000, self.periodic_ui)

    def load_config(self):
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                self.selected_port.set(data.get("port", "-"))
                self.s1 = int(data.get("s1", self.s1))
                self.s2 = int(data.get("s2", self.s2))
            except Exception:
                pass

    def save_config(self):
        data = {"port": self.selected_port.get(), "s1": self.s1, "s2": self.s2}
        CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkScrollableFrame(self, width=270, corner_radius=0, fg_color=COLORS["sidebar"])
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.main = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew", padx=18, pady=18)
        self.main.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.main.grid_rowconfigure(0, weight=0, minsize=54)
        self.main.grid_rowconfigure(1, weight=0, minsize=76)
        self.main.grid_rowconfigure(2, weight=0, minsize=158)
        self.main.grid_rowconfigure(3, weight=1, minsize=268)
        self.main.grid_rowconfigure(4, weight=0, minsize=176)

        self.build_sidebar()
        self.build_main()

    def build_sidebar(self):
        ctk.CTkLabel(
            self.sidebar,
            text="SPIROB\nMISSION CONTROL",
            font=("Arial", 24, "bold"),
            justify="left",
        ).pack(anchor="w", padx=18, pady=(22, 4))

        ctk.CTkLabel(
            self.sidebar,
            text="Bluetooth kontrolni interfejs\nHC-06 • STM32F103C8T6 • Servo drive",
            text_color=COLORS["muted"],
            justify="left",
            font=("Arial", 12),
        ).pack(anchor="w", padx=18)

        connection = self.card(self.sidebar, "KONEKCIJA")
        self.port_menu = ctk.CTkOptionMenu(connection, values=["-"], variable=self.selected_port, height=34)
        self.port_menu.pack(fill="x", pady=(8, 8))
        ctk.CTkButton(connection, text="OSVJEŽI PORTOVE", command=self.refresh_ports, height=36).pack(fill="x", pady=5)
        ctk.CTkButton(connection, text="POVEŽI SISTEM", command=self.connect, height=40, fg_color=COLORS["blue"]).pack(fill="x", pady=5)
        ctk.CTkButton(connection, text="PREKINI VEZU", command=self.disconnect, height=36, fg_color=COLORS["disabled"]).pack(fill="x", pady=5)

        hw = self.card(self.sidebar, "HARDVER MAPA")
        self.pin_canvas = ctk.CTkCanvas(hw, width=214, height=166, bg=COLORS["card"], highlightthickness=0)
        self.pin_canvas.pack(pady=4)
        self.draw_hardware_map(False)

        info = [
            ("Baud", "9600"),
            ("Bluetooth", "HC-06"),
            ("MCU", "STM32F103C8T6"),
            ("BT TX/RX", "PA9 / PA10"),
            ("Servo 1", "PA0"),
            ("Servo 2", "PA1"),
            ("Power", "vanjski 5V/6V"),
        ]
        for a, b in info:
            row = ctk.CTkFrame(hw, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f"{a}:", width=80, anchor="w", font=("Consolas", 11), text_color=COLORS["soft"]).pack(side="left")
            ctk.CTkLabel(row, text=b, anchor="w", font=("Consolas", 11, "bold")).pack(side="left")

        indicators = self.card(self.sidebar, "INDIKATORI")
        indicator_grid = ctk.CTkFrame(indicators, fg_color="transparent")
        indicator_grid.pack(fill="x", pady=(8, 4))
        indicator_grid.grid_columnconfigure((0, 1), weight=1)

        self.grip_indicator = RoundIndicator(indicator_grid, "GRIP", 0, COLORS["green"])
        self.grip_indicator.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        self.link_indicator = RoundIndicator(indicator_grid, "LINK", 0, "#60a5fa")
        self.link_indicator.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        ctk.CTkLabel(
            indicators,
            text="Digital Twin prikazuje stanje iz\nACK/STATE odgovora STM32 kontrolera.",
            text_color=COLORS["muted"],
            justify="left",
            font=("Arial", 11),
        ).pack(anchor="w", pady=(8, 0))

    def build_main(self):
        self.status_bar = ctk.CTkFrame(self.main, fg_color=COLORS["card"], corner_radius=18)
        self.status_bar.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 12))
        self.status_bar.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(self.status_bar, text="● OFFLINE", text_color=COLORS["red"], font=("Arial", 18, "bold"))
        self.status_label.grid(row=0, column=0, padx=20, pady=14, sticky="w")
        self.latency_label = ctk.CTkLabel(self.status_bar, text="Latency: - ms    COM: -", font=("Consolas", 12))
        self.latency_label.grid(row=0, column=1, padx=20, sticky="e")

        self.metric_command = self.metric(1, 0, "ZADNJA KOMANDA", self.last_command, COLORS["blue"])
        self.metric_mode = self.metric(1, 1, "REŽIM RADA", "Ručno", "#ffffff")
        self.metric_s1 = self.metric(1, 2, "SERVO 1", f"{self.s1}°", "#facc15")
        self.metric_s2 = self.metric(1, 3, "SERVO 2", f"{self.s2}°", "#facc15")

        control = ctk.CTkFrame(self.main, fg_color=COLORS["card"], corner_radius=18, height=158)
        control.grid(row=2, column=0, columnspan=4, sticky="nsew", pady=(0, 10))
        control.grid_propagate(False)
        control.grid_columnconfigure((0, 1, 2, 3), weight=1)
        ctk.CTkLabel(control, text="Upravljanje", font=("Arial", 18, "bold")).grid(row=0, column=0, sticky="w", padx=18, pady=(14, 8))
        self.command_button(control, "UHVATI", "g", COLORS["blue"], 1, 0, "Start sekvence")
        self.command_button(control, "E-STOP / PUSTI", "f", COLORS["red2"], 1, 1, "Sigurno zaustavljanje")
        self.command_button(control, "HOME", "h", COLORS["disabled"], 1, 2, "Početni položaj")
        self.command_button(control, "OTVORI", "o", COLORS["disabled"], 1, 3, "Otpuštanje")
        self.command_button(control, "ZATEGNI", "c", COLORS["disabled"], 2, 0, "Finalni grip")
        self.command_button(control, "TEST S1", "1", COLORS["amber"], 2, 1, "Dijagnostika")
        self.command_button(control, "TEST S2", "2", COLORS["amber"], 2, 2, "Dijagnostika")
        self.command_button(control, "PING", "?", COLORS["amber"], 2, 3, "Provjera veze")

        twin = ctk.CTkFrame(self.main, fg_color=COLORS["card"], corner_radius=18)
        twin.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=(0, 8), pady=(0, 12))
        ctk.CTkLabel(twin, text="Digital Twin / Wireframe", font=("Arial", 18, "bold")).pack(anchor="w", padx=18, pady=(14, 4))
        self.twin_canvas = ctk.CTkCanvas(twin, height=220, bg=COLORS["card2"], highlightthickness=0)
        self.twin_canvas.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        self.build_calibration_panel()

        log_frame = ctk.CTkFrame(self.main, fg_color=COLORS["card"], corner_radius=18, height=176)
        log_frame.grid(row=4, column=0, columnspan=4, sticky="nsew")
        log_frame.grid_propagate(False)
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1, minsize=96)

        top = ctk.CTkFrame(log_frame, fg_color="transparent", height=36)
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=(10, 4))
        top.grid_propagate(False)
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            top,
            text="Napredni komunikacijski log",
            font=("Arial", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")

        button_bar = ctk.CTkFrame(top, fg_color="transparent")
        button_bar.grid(row=0, column=1, sticky="e")

        ctk.CTkButton(button_bar, text="CLEAR", width=70, height=28, command=self.clear_log, fg_color=COLORS["disabled"]).pack(side="left", padx=4)
        ctk.CTkButton(button_bar, text="EXPORT", width=80, height=28, command=self.export_log, fg_color=COLORS["disabled"]).pack(side="left", padx=4)
        ctk.CTkButton(button_bar, text="PLAY MACRO", width=100, height=28, command=self.play_macro).pack(side="left", padx=4)
        ctk.CTkButton(button_bar, text="REC MACRO", width=95, height=28, command=self.toggle_record).pack(side="left", padx=4)

        self.log_text = ctk.CTkTextbox(
            log_frame,
            fg_color="#020617",
            border_width=1,
            border_color=COLORS["border"],
            corner_radius=12,
            font=("Consolas", 12),
            wrap="none",
            height=98,
        )
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))

    def build_calibration_panel(self):
        calib = ctk.CTkFrame(self.main, fg_color=COLORS["card"], corner_radius=18)
        calib.grid(row=3, column=2, columnspan=2, sticky="nsew", padx=(8, 0), pady=(0, 10))
        calib.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(calib, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(14, 6))
        ctk.CTkLabel(head, text="Kalibracija pokreta", font=("Arial", 18, "bold")).pack(side="left")

        live = ctk.CTkSwitch(
            head,
            text="LIVE",
            variable=self.live_calibration,
            command=self.on_live_toggle,
            progress_color=COLORS["green"],
            button_color="#e5e7eb",
            font=("Arial", 12, "bold"),
        )
        live.pack(side="right")

        ctk.CTkLabel(
            calib,
            text="Slider mijenja preview. Za siguran rad klikni PRIMIJENI OBA; za direktno pomjeranje uključi LIVE.",
            text_color=COLORS["muted"],
            font=("Arial", 11),
            wraplength=620,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 10))

        self.s1_value_label, self.slider1 = self.calibration_slider(
            calib,
            "Servo 1",
            "PA0",
            self.s1,
            lambda v: self.on_slider_change("A", int(float(v))),
        )
        self.s2_value_label, self.slider2 = self.calibration_slider(
            calib,
            "Servo 2",
            "PA1",
            self.s2,
            lambda v: self.on_slider_change("B", int(float(v))),
        )

        quick = ctk.CTkFrame(calib, fg_color="transparent")
        quick.pack(fill="x", padx=18, pady=(5, 7))
        quick.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(
            quick,
            text="PRIMIJENI OBA",
            command=self.apply_both_servos,
            height=34,
            fg_color=COLORS["blue"],
            font=("Arial", 12, "bold"),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            quick,
            text="HOME SET",
            command=self.set_home_preview,
            height=34,
            fg_color=COLORS["disabled"],
            font=("Arial", 12, "bold"),
        ).grid(row=0, column=1, sticky="ew", padx=6)

        ctk.CTkButton(
            quick,
            text="GRIP SET",
            command=self.set_grip_preview,
            height=34,
            fg_color=COLORS["disabled"],
            font=("Arial", 12, "bold"),
        ).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        self.live_hint = ctk.CTkLabel(
            calib,
            text="LIVE isključen: podešavanje je sigurno i ne šalje komande dok ne klikneš PRIMIJENI OBA.",
            text_color=COLORS["muted"],
            font=("Consolas", 11),
        )
        self.live_hint.pack(anchor="w", padx=18, pady=(0, 8))

    def calibration_slider(self, parent, name, pin, value, callback):
        box = ctk.CTkFrame(parent, fg_color=COLORS["card2"], corner_radius=16)
        box.pack(fill="x", padx=18, pady=5)
        box.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(box, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(9, 0))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text=f"{name} ugao", font=("Arial", 13, "bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(top, text=pin, text_color=COLORS["muted"], font=("Consolas", 11, "bold")).grid(row=0, column=1, sticky="w", padx=12)

        value_label = ctk.CTkLabel(
            top,
            text=f"{value}°",
            width=64,
            height=28,
            corner_radius=14,
            fg_color="#1f2937",
            text_color="#facc15",
            font=("Consolas", 15, "bold"),
        )
        value_label.grid(row=0, column=2, sticky="e")

        slider = ctk.CTkSlider(box, from_=0, to=180, command=callback, progress_color="#64748b", button_color="#1f77b4")
        slider.set(value)
        slider.grid(row=1, column=0, sticky="ew", padx=14, pady=(5, 7))

        marks = ctk.CTkFrame(box, fg_color="transparent")
        marks.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 6))
        marks.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkLabel(marks, text="0°", text_color=COLORS["muted"], font=("Consolas", 9)).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(marks, text="90°", text_color=COLORS["muted"], font=("Consolas", 9)).grid(row=0, column=1)
        ctk.CTkLabel(marks, text="180°", text_color=COLORS["muted"], font=("Consolas", 9)).grid(row=0, column=2, sticky="e")

        return value_label, slider

    def card(self, parent, title):
        frame = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=18)
        frame.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(frame, text=title, text_color="#60a5fa", font=("Arial", 13, "bold")).pack(anchor="w", padx=14, pady=(14, 4))
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=(4, 14))
        return inner

    def metric(self, row, col, label, value, color):
        frame = ctk.CTkFrame(self.main, fg_color=COLORS["card"], corner_radius=16)
        frame.grid(row=row, column=col, sticky="ew", padx=6, pady=(0, 12))
        ctk.CTkLabel(frame, text=label, text_color="#93c5fd", font=("Arial", 11, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        value_label = ctk.CTkLabel(frame, text=value, text_color=color, font=("Arial", 20, "bold"))
        value_label.pack(anchor="w", padx=16, pady=(0, 14))
        return value_label

    def command_button(self, parent, text, cmd, color, row, col, subtitle):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(row=row, column=col, sticky="ew", padx=16, pady=5)
        button = ctk.CTkButton(box, text=text, command=lambda: self.send_command(cmd), height=36, fg_color=color, font=("Arial", 12, "bold"))
        button.pack(fill="x")
        ctk.CTkLabel(box, text=subtitle, text_color=COLORS["muted"], font=("Arial", 9)).pack(pady=(3, 0))

    def draw_hardware_map(self, active):
        c = self.pin_canvas
        c.delete("all")
        c.create_rectangle(70, 25, 150, 132, outline="#4b5563", width=2)
        c.create_text(110, 60, text="STM32\nF103C8T6", fill="white", font=("Consolas", 10, "bold"))
        pins = [(34, 62, "PA10 RX"), (34, 88, "PA9 TX"), (176, 62, "PA0 S1"), (176, 88, "PA1 S2")]
        for x, y, label in pins:
            fill = "#60a5fa" if active else "#64748b"
            c.create_oval(x - 6, y - 6, x + 6, y + 6, fill=fill, outline="")
            c.create_text(x - 10 if x < 100 else x + 10, y, text=label, fill="white", font=("Consolas", 8), anchor="e" if x < 100 else "w")
        c.create_oval(104, 115, 116, 127, fill=COLORS["green"], outline="")
        c.create_text(110, 146, text="GND", fill="white", font=("Consolas", 8))

    def draw_twin(self):
        c = self.twin_canvas
        c.delete("all")
        w = max(c.winfo_width(), 500)
        h = max(c.winfo_height(), 230)
        cx, cy = w / 2, h / 2 + 10
        grip = self.grip / 100
        c.create_text(24, 24, text=f"Grip intensity: {self.grip}%", anchor="w", fill="white", font=("Consolas", 13, "bold"))
        c.create_oval(cx - 55, cy - 55, cx + 55, cy + 55, outline="#334155", width=2)
        c.create_text(cx, cy, text="GRAPPLER", fill="white", font=("Arial", 11, "bold"))
        for i in range(6):
            a = math.radians(i * 60 - 90)
            curl = math.radians(20 + 55 * grip)
            x0 = cx + math.cos(a) * 62
            y0 = cy + math.sin(a) * 62
            x1 = x0 + math.cos(a + curl) * 75
            y1 = y0 + math.sin(a + curl) * 75
            x2 = x1 + math.cos(a + curl * 1.35) * 45
            y2 = y1 + math.sin(a + curl * 1.35) * 45
            c.create_line(x0, y0, x1, y1, fill="#60a5fa", width=4)
            c.create_line(x1, y1, x2, y2, fill="#60a5fa", width=3)
            c.create_oval(x0 - 5, y0 - 5, x0 + 5, y0 + 5, fill=COLORS["card"], outline="#93c5fd")
            c.create_oval(x2 - 3, y2 - 3, x2 + 3, y2 + 3, fill="#60a5fa", outline="")

    def refresh_ports(self):
        ports = [p.device for p in list_ports.comports()]
        if not ports:
            ports = ["-"]
        self.port_menu.configure(values=ports)
        if self.selected_port.get() not in ports:
            self.selected_port.set(ports[0])
        self.log("INFO", "Pronađeni portovi: " + ", ".join(ports))

    def connect(self):
        port = self.selected_port.get()
        if port == "-":
            self.log("WARN", "Nije izabran COM port.")
            return
        try:
            self.ser = serial.Serial(port, BAUD, timeout=0.1)
            self.connected = True
            self.reader_alive = True
            self.reader_thread = threading.Thread(target=self.reader_loop, daemon=True)
            self.reader_thread.start()
            self.save_config()
            self.log("OK", f"Povezano na {port} pri {BAUD} baud.")
            self.send_command("?")
        except Exception as e:
            self.log("ERROR", f"Ne mogu otvoriti {port}: {e}")

    def disconnect(self):
        self.reader_alive = False
        self.connected = False
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.log("INFO", "Konekcija prekinuta.")

    def send_command(self, cmd):
        if not self.connected or not self.ser or not self.ser.is_open:
            self.log("WARN", "Sistem nije povezan.")
            return False
        frame = f"<{cmd}>"
        try:
            self.ser.write(frame.encode("ascii"))
            self.ser.flush()
            self.last_command = cmd
            self.metric_command.configure(text=cmd)
            self.log("TX", frame)
            if self.recording:
                self.macro.append(cmd)
            return True
        except Exception as e:
            self.log("ERROR", f"Slanje nije uspjelo: {e}")
            return False

    def reader_loop(self):
        buf = ""
        while self.reader_alive and self.ser:
            try:
                data = self.ser.read(128)
                if data:
                    text = data.decode("utf-8", errors="ignore")
                    for ch in text:
                        if ch == "\n":
                            line = buf.strip()
                            buf = ""
                            if line:
                                self.after(0, lambda l=line: self.handle_rx(l))
                        elif ch != "\r":
                            buf += ch
                else:
                    time.sleep(0.02)
            except Exception as e:
                self.after(0, lambda: self.log("ERROR", f"Reader error: {e}"))
                break

    def handle_rx(self, line):
        self.log("RX", line)
        if line.startswith("ACK:"):
            self.last_ack_time = time.time()
        if line.startswith("STATE:"):
            self.parse_state(line)

    def parse_state(self, line):
        try:
            payload = line.split(":", 1)[1]
            data = dict(item.split("=", 1) for item in payload.split(";") if "=" in item)
            self.s1 = int(data.get("S1", self.s1))
            self.s2 = int(data.get("S2", self.s2))
            self.grip = int(data.get("GRIP", self.grip))
            self.slider1.set(self.s1)
            self.slider2.set(self.s2)
            self.update_metrics()
            self.draw_twin()
        except Exception as e:
            self.log("WARN", f"Ne mogu parsirati STATE: {e}")

    def on_slider_change(self, servo, value):
        if servo == "A":
            self.s1 = value
            self.s1_value_label.configure(text=f"{value}°")
            self.schedule_live_send("A", value)
        else:
            self.s2 = value
            self.s2_value_label.configure(text=f"{value}°")
            self.schedule_live_send("B", value)

        self.grip = self.estimate_grip()
        self.update_metrics()
        self.draw_twin()

    def schedule_live_send(self, servo, value):
        if not self.live_calibration.get():
            return

        attr = "pending_live_job_s1" if servo == "A" else "pending_live_job_s2"
        old_job = getattr(self, attr)
        if old_job is not None:
            try:
                self.after_cancel(old_job)
            except Exception:
                pass

        job = self.after(160, lambda s=servo, v=value: self.send_command(f"{s}{v:03d}"))
        setattr(self, attr, job)

    def on_live_toggle(self):
        if self.live_calibration.get():
            self.metric_mode.configure(text="Live kalibracija")
            self.live_hint.configure(
                text="LIVE uključen: servo se pomjera dok pomjeraš slider, ali sa kratkim debounce kašnjenjem da se ne spamuje Bluetooth.",
                text_color=COLORS["amber"],
            )
            self.log("INFO", "LIVE kalibracija uključena.")
        else:
            self.metric_mode.configure(text="Ručno")
            self.live_hint.configure(
                text="LIVE isključen: podešavanje je sigurno i ne šalje komande dok ne klikneš PRIMIJENI OBA.",
                text_color=COLORS["muted"],
            )
            self.log("INFO", "LIVE kalibracija isključena.")

    def apply_both_servos(self):
        ok1 = self.send_command(f"A{self.s1:03d}")
        if ok1:
            self.after(180, lambda: self.send_command(f"B{self.s2:03d}"))
            self.save_config()

    def set_home_preview(self):
        self.s1 = SERVO1_HOME
        self.s2 = SERVO2_HOME
        self.slider1.set(self.s1)
        self.slider2.set(self.s2)
        self.s1_value_label.configure(text=f"{self.s1}°")
        self.s2_value_label.configure(text=f"{self.s2}°")
        self.grip = self.estimate_grip()
        self.update_metrics()
        self.draw_twin()
        self.log("INFO", "Preview postavljen na HOME. Klikni PRIMIJENI OBA za slanje.")

    def set_grip_preview(self):
        self.s1 = SERVO1_GRIP
        self.s2 = SERVO2_GRIP
        self.slider1.set(self.s1)
        self.slider2.set(self.s2)
        self.s1_value_label.configure(text=f"{self.s1}°")
        self.s2_value_label.configure(text=f"{self.s2}°")
        self.grip = self.estimate_grip()
        self.update_metrics()
        self.draw_twin()
        self.log("INFO", "Preview postavljen na GRIP. Klikni PRIMIJENI OBA za slanje.")

    def estimate_grip(self):
        p1 = max(0, min(1, (SERVO1_HOME - self.s1) / max(1, SERVO1_HOME - SERVO1_GRIP)))
        p2 = max(0, min(1, (self.s2 - SERVO2_HOME) / max(1, SERVO2_GRIP - SERVO2_HOME)))
        return int((p1 + p2) * 50)

    def update_metrics(self):
        self.metric_s1.configure(text=f"{self.s1}°")
        self.metric_s2.configure(text=f"{self.s2}°")
        self.grip_indicator.draw(self.grip)

    def periodic_ui(self):
        self.status_label.configure(
            text="● ONLINE" if self.connected else "● OFFLINE",
            text_color=COLORS["green"] if self.connected else COLORS["red"],
        )

        self.link_indicator.draw(100 if self.connected else 0)
        self.grip_indicator.draw(self.grip)
        self.draw_hardware_map(self.connected)

        latency = "-"
        if self.last_ack_time and self.connected:
            latency = str(int((time.time() - self.last_ack_time) * 1000))
        self.latency_label.configure(text=f"Latency: {latency} ms    COM: {self.selected_port.get()}")

        self.after(1000, self.periodic_ui)

    def toggle_record(self):
        self.recording = not self.recording
        if self.recording:
            self.macro = []
            self.log("INFO", "Snimanje macro sekvence pokrenuto.")
        else:
            self.log("INFO", f"Macro snimljen: {self.macro}")

    def play_macro(self):
        if not self.macro:
            self.log("WARN", "Macro je prazan.")
            return

        def worker():
            for cmd in self.macro:
                self.after(0, lambda c=cmd: self.send_command(c))
                time.sleep(0.7)

        threading.Thread(target=worker, daemon=True).start()

    def export_log(self):
        data = {"exported_at": datetime.now().isoformat(), "logs": self.logs, "macro": self.macro}
        LOG_EXPORT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.log("OK", f"Log exportovan u {LOG_EXPORT_PATH}")

    def clear_log(self):
        self.logs.clear()
        self.log_text.delete("1.0", "end")

    def log(self, level, message):
        line = f"[{now()}] [{level}] {message}"
        self.logs.append(line)
        if len(self.logs) > 300:
            self.logs = self.logs[-300:]
        try:
            self.log_text.insert("end", line + "\n")
            self.log_text.see("end")
        except Exception:
            pass


if __name__ == "__main__":
    app = GrapplerApp()
    app.mainloop()
