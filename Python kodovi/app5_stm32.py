import json
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
    "bg": "#070b14",
    "card": "#111827",
    "card2": "#0b1220",
    "blue": "#2563eb",
    "red": "#ef4444",
    "amber": "#f59e0b",
    "green": "#22c55e",
    "muted": "#94a3b8",
    "border": "#26364d",
}


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


class GrapplerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1500x900")
        self.minsize(1180, 760)
        self.configure(fg_color=COLORS["bg"])

        self.ser = None
        self.reader_alive = False
        self.reader_thread = None
        self.connected = False
        self.last_ack_time = None
        self.logs = []
        self.recording = False
        self.macro = []

        self.s1 = 175
        self.s2 = 5
        self.grip = 0
        self.last_command = "Nema"
        self.selected_port = ctk.StringVar(value="-")

        self.load_config()
        self.build_ui()
        self.refresh_ports()
        self.after(1000, self.periodic_ui)

    def load_config(self):
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                self.selected_port.set(data.get("port", "-"))
            except Exception:
                pass

    def save_config(self):
        CONFIG_PATH.write_text(json.dumps({"port": self.selected_port.get()}, indent=2), encoding="utf-8")

    def build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkScrollableFrame(self, width=260, corner_radius=0, fg_color="#090f1c")
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.main = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew", padx=18, pady=18)
        self.main.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.main.grid_rowconfigure(4, weight=1)

        self.build_sidebar()
        self.build_main()

    def build_sidebar(self):
        ctk.CTkLabel(self.sidebar, text="SPIROB\nMISSION CONTROL", font=("Arial", 24, "bold"), justify="left").pack(anchor="w", padx=18, pady=(22, 4))
        ctk.CTkLabel(self.sidebar, text="Bluetooth kontrolni interfejs\nHC-06 • STM32F103C8T6 • Servo pogon", text_color=COLORS["muted"], justify="left").pack(anchor="w", padx=18)

        connection = self.card(self.sidebar, "KONEKCIJA")
        self.port_menu = ctk.CTkOptionMenu(connection, values=["-"], variable=self.selected_port, height=34)
        self.port_menu.pack(fill="x", pady=(8, 8))
        ctk.CTkButton(connection, text="OSVJEŽI PORTOVE", command=self.refresh_ports, height=36).pack(fill="x", pady=5)
        ctk.CTkButton(connection, text="POVEŽI SISTEM", command=self.connect, height=40, fg_color=COLORS["blue"]).pack(fill="x", pady=5)
        ctk.CTkButton(connection, text="PREKINI VEZU", command=self.disconnect, height=36, fg_color="#334155").pack(fill="x", pady=5)

        hw = self.card(self.sidebar, "HARDVER MAPA")
        self.pin_canvas = ctk.CTkCanvas(hw, width=210, height=160, bg=COLORS["card"], highlightthickness=0)
        self.pin_canvas.pack(pady=4)
        self.draw_hardware_map(False)
        info = [
            ("Baud rate", "9600"),
            ("Bluetooth", "HC-06"),
            ("MCU", "STM32F103C8T6"),
            ("BT TX/RX", "PA9 / PA10"),
            ("Servo 1", "PA0"),
            ("Servo 2", "PA1"),
            ("Napajanje", "vanjski 5V/6V"),
        ]
        for a, b in info:
            row = ctk.CTkFrame(hw, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f"{a}:", width=84, anchor="w", font=("Consolas", 12), text_color="#cbd5e1").pack(side="left")
            ctk.CTkLabel(row, text=b, anchor="w", font=("Consolas", 12, "bold")).pack(side="left")

        indicators = self.card(self.sidebar, "INDIKATORI")
        row = ctk.CTkFrame(indicators, fg_color="transparent")
        row.pack(fill="x", pady=12)
        self.grip_label = self.gauge(row, "0%\nGRIP")
        self.link_label = self.gauge(row, "0%\nLINK")
        ctk.CTkLabel(indicators, text="Digital Twin prikazuje stanje na osnovu\nACK/STATE odgovora STM32 kontrolera.", text_color=COLORS["muted"], justify="left", font=("Arial", 11)).pack(anchor="w", pady=(8, 0))

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

        control = ctk.CTkFrame(self.main, fg_color=COLORS["card"], corner_radius=18)
        control.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(0, 12))
        control.grid_columnconfigure((0, 1, 2, 3), weight=1)
        ctk.CTkLabel(control, text="Upravljanje", font=("Arial", 18, "bold")).grid(row=0, column=0, sticky="w", padx=18, pady=(14, 8))
        self.command_button(control, "UHVATI", "g", COLORS["blue"], 1, 0)
        self.command_button(control, "E-STOP / PUSTI", "f", COLORS["red"], 1, 1)
        self.command_button(control, "HOME", "h", "#334155", 1, 2)
        self.command_button(control, "OTVORI", "o", "#334155", 1, 3)
        self.command_button(control, "ZATEGNI", "c", "#334155", 2, 0)
        self.command_button(control, "TEST S1", "1", COLORS["amber"], 2, 1)
        self.command_button(control, "TEST S2", "2", COLORS["amber"], 2, 2)
        self.command_button(control, "PING", "?", COLORS["amber"], 2, 3)

        twin = ctk.CTkFrame(self.main, fg_color=COLORS["card"], corner_radius=18)
        twin.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=(0, 8), pady=(0, 12))
        ctk.CTkLabel(twin, text="Digital Twin / Wireframe", font=("Arial", 18, "bold")).pack(anchor="w", padx=18, pady=(14, 4))
        self.twin_canvas = ctk.CTkCanvas(twin, height=250, bg=COLORS["card2"], highlightthickness=0)
        self.twin_canvas.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        calib = ctk.CTkFrame(self.main, fg_color=COLORS["card"], corner_radius=18)
        calib.grid(row=3, column=2, columnspan=2, sticky="nsew", padx=(8, 0), pady=(0, 12))
        ctk.CTkLabel(calib, text="Kalibracija pokreta", font=("Arial", 18, "bold")).pack(anchor="w", padx=18, pady=(14, 10))
        self.slider1 = self.slider_row(calib, "Servo 1 ugao", 0, 180, self.s1, lambda v: self.set_s1(int(float(v))))
        self.slider2 = self.slider_row(calib, "Servo 2 ugao", 0, 180, self.s2, lambda v: self.set_s2(int(float(v))))
        ctk.CTkButton(calib, text="POŠALJI S1", command=lambda: self.send_command(f"A{self.s1:03d}"), height=35).pack(fill="x", padx=18, pady=(15, 5))
        ctk.CTkButton(calib, text="POŠALJI S2", command=lambda: self.send_command(f"B{self.s2:03d}"), height=35).pack(fill="x", padx=18, pady=5)

        log_frame = ctk.CTkFrame(self.main, fg_color=COLORS["card"], corner_radius=18)
        log_frame.grid(row=4, column=0, columnspan=4, sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)
        top = ctk.CTkFrame(log_frame, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=(12, 4))
        ctk.CTkLabel(top, text="Napredni komunikacijski log", font=("Arial", 18, "bold")).pack(side="left")
        ctk.CTkButton(top, text="REC MACRO", width=90, command=self.toggle_record).pack(side="right", padx=5)
        ctk.CTkButton(top, text="PLAY MACRO", width=95, command=self.play_macro).pack(side="right", padx=5)
        ctk.CTkButton(top, text="EXPORT", width=80, command=self.export_log, fg_color="#334155").pack(side="right", padx=5)
        ctk.CTkButton(top, text="CLEAR", width=70, command=self.clear_log, fg_color="#334155").pack(side="right", padx=5)
        self.log_text = ctk.CTkTextbox(log_frame, fg_color="#020617", font=("Consolas", 12), wrap="none")
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 16))

        self.draw_twin()

    def card(self, parent, title):
        frame = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=18)
        frame.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(frame, text=title, text_color="#60a5fa", font=("Arial", 13, "bold")).pack(anchor="w", padx=14, pady=(14, 4))
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=(4, 14))
        return inner

    def gauge(self, parent, text):
        label = ctk.CTkLabel(parent, text=text, width=95, height=95, corner_radius=48, fg_color="#1f2937", font=("Consolas", 16, "bold"))
        label.pack(side="left", expand=True, padx=4)
        return label

    def metric(self, row, col, label, value, color):
        frame = ctk.CTkFrame(self.main, fg_color=COLORS["card"], corner_radius=16)
        frame.grid(row=row, column=col, sticky="ew", padx=6, pady=(0, 12))
        ctk.CTkLabel(frame, text=label, text_color="#93c5fd", font=("Arial", 11, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        value_label = ctk.CTkLabel(frame, text=value, text_color=color, font=("Arial", 20, "bold"))
        value_label.pack(anchor="w", padx=16, pady=(0, 14))
        return value_label

    def command_button(self, parent, text, cmd, color, row, col):
        button = ctk.CTkButton(parent, text=text, command=lambda: self.send_command(cmd), height=42, fg_color=color)
        button.grid(row=row, column=col, sticky="ew", padx=18, pady=10)

    def slider_row(self, parent, title, a, b, value, callback):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=10)
        label = ctk.CTkLabel(row, text=title, font=("Arial", 13, "bold"))
        label.pack(anchor="w")
        slider = ctk.CTkSlider(row, from_=a, to=b, command=callback)
        slider.set(value)
        slider.pack(fill="x", pady=6)
        return slider

    def draw_hardware_map(self, active):
        c = self.pin_canvas
        c.delete("all")
        c.create_rectangle(70, 25, 150, 130, outline="#4b5563", width=2)
        c.create_text(110, 58, text="STM32\nF103C8T6", fill="white", font=("Consolas", 10, "bold"))
        pins = [(35, 62, "PA10 RX"), (35, 88, "PA9 TX"), (175, 62, "PA0 S1"), (175, 88, "PA1 S2")]
        for x, y, label in pins:
            c.create_oval(x - 6, y - 6, x + 6, y + 6, fill="#60a5fa" if active else "#64748b", outline="")
            c.create_text(x - 10 if x < 100 else x + 10, y, text=label, fill="white", font=("Consolas", 8), anchor="e" if x < 100 else "w")
        c.create_oval(104, 113, 116, 125, fill=COLORS["green"], outline="")
        c.create_text(110, 138, text="GND", fill="white", font=("Consolas", 8))

    def draw_twin(self):
        c = self.twin_canvas
        c.delete("all")
        w = max(c.winfo_width(), 500)
        h = max(c.winfo_height(), 220)
        cx, cy = w / 2, h / 2 + 5
        grip = self.grip / 100
        c.create_text(24, 24, text=f"Grip intensity: {self.grip}%", anchor="w", fill="white", font=("Consolas", 13, "bold"))
        c.create_oval(cx - 55, cy - 55, cx + 55, cy + 55, outline="#334155", width=2)
        c.create_text(cx, cy, text="GRAPPLER", fill="white", font=("Arial", 11, "bold"))
        import math
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
            return
        frame = f"<{cmd}>"
        try:
            self.ser.write(frame.encode("ascii"))
            self.ser.flush()
            self.last_command = cmd
            self.metric_command.configure(text=cmd)
            self.log("TX", frame)
            if self.recording:
                self.macro.append(cmd)
        except Exception as e:
            self.log("ERROR", f"Slanje nije uspjelo: {e}")

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
            self.update_metrics()
            self.draw_twin()
        except Exception as e:
            self.log("WARN", f"Ne mogu parsirati STATE: {e}")

    def set_s1(self, value):
        self.s1 = value
        self.update_metrics()
        self.grip = self.estimate_grip()
        self.draw_twin()

    def set_s2(self, value):
        self.s2 = value
        self.update_metrics()
        self.grip = self.estimate_grip()
        self.draw_twin()

    def estimate_grip(self):
        p1 = max(0, min(1, (175 - self.s1) / 170))
        p2 = max(0, min(1, (self.s2 - 5) / 170))
        return int((p1 + p2) * 50)

    def update_metrics(self):
        self.metric_s1.configure(text=f"{self.s1}°")
        self.metric_s2.configure(text=f"{self.s2}°")
        self.grip_label.configure(text=f"{self.grip}%\nGRIP")

    def periodic_ui(self):
        self.status_label.configure(text="● ONLINE" if self.connected else "● OFFLINE", text_color=COLORS["green"] if self.connected else COLORS["red"])
        self.link_label.configure(text="100%\nLINK" if self.connected else "0%\nLINK")
        self.draw_hardware_map(self.connected)
        latency = "-"
        if self.last_ack_time:
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
