import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import serial
from serial.tools import list_ports
from datetime import datetime
import time
import csv
import json
import math

BAUD = 9600
DEFAULT_PORT = "COM4"

SERVO1_HOME = 175
SERVO2_HOME = 5
SERVO1_PULL = 5
SERVO2_PULL = 175
SERVO1_MID = 90
SERVO2_MID = 90

COLOR_INFO = "#2563eb"
COLOR_INFO_HOVER = "#1d4ed8"
COLOR_SUCCESS = "#16a34a"
COLOR_WARNING = "#f59e0b"
COLOR_WARNING_HOVER = "#d97706"
COLOR_DANGER = "#dc2626"
COLOR_DANGER_HOVER = "#b91c1c"
COLOR_NEUTRAL = "#334155"
COLOR_NEUTRAL_HOVER = "#475569"
COLOR_SURFACE = "#111827"
COLOR_SURFACE_2 = "#0f172a"
COLOR_BG = "#070b14"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class SerialManager:
    def __init__(self):
        self.ser = None
        self.port = None

    def connect(self, port):
        self.disconnect()
        self.ser = serial.Serial(port, BAUD, timeout=0.05)
        self.port = port

    def disconnect(self):
        if self.ser is not None:
            try:
                if self.ser.is_open:
                    self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.port = None

    def connected(self):
        return self.ser is not None and self.ser.is_open

    def write(self, text):
        if not self.connected():
            raise serial.SerialException("Serial port nije povezan")
        self.ser.write(text.encode("ascii", errors="ignore"))
        self.ser.flush()

    def read_lines(self):
        if not self.connected():
            return []
        out = []
        while self.ser.in_waiting:
            line = self.ser.readline().decode(errors="ignore").strip()
            if line:
                out.append(line)
        return out


class GrapplerUltraApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SpiRob Grappler Mission Control")
        self.geometry("1280x800")
        self.minsize(1120, 720)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.serial = SerialManager()
        self.logs = []
        self.log_filter = "ALL"
        self.pending_ping = None
        self.animation_handles = []
        self.updating_sliders = False
        self.recording = False
        self.macro_events = []
        self.record_start = 0

        self.servo1_angle = SERVO1_HOME
        self.servo2_angle = SERVO2_HOME
        self.grip_intensity = 0

        self.configure(bg=COLOR_BG)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.build_sidebar()
        self.build_main()
        self.refresh_ports()
        self.set_connected_ui(False)
        self.log("Aplikacija pokrenuta. Izaberi HC-06 COM port i klikni Poveži sistem.", "INFO")

        self.after(120, self.auto_read)
        self.after(160, self.redraw_visuals)

    def build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=310, corner_radius=0, fg_color="#0b1220")
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(10, weight=1)

        ctk.CTkLabel(
            self.sidebar,
            text="SPIROB\nMISSION CONTROL",
            font=ctk.CTkFont(size=27, weight="bold"),
            text_color="#f8fafc",
            justify="left",
        ).grid(row=0, column=0, padx=26, pady=(26, 4), sticky="w")

        ctk.CTkLabel(
            self.sidebar,
            text="Bluetooth Control Interface\nHC-06 • Arduino Uno • Servo Drive",
            font=ctk.CTkFont(size=13),
            text_color="#94a3b8",
            justify="left",
        ).grid(row=1, column=0, padx=26, pady=(0, 22), sticky="w")

        self.connection_card = ctk.CTkFrame(self.sidebar, corner_radius=20, fg_color=COLOR_SURFACE)
        self.connection_card.grid(row=2, column=0, padx=20, pady=8, sticky="ew")
        self.connection_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.connection_card,
            text="KONEKCIJA",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#60a5fa",
        ).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        self.port_var = ctk.StringVar(value="")
        self.port_menu = ctk.CTkOptionMenu(
            self.connection_card,
            variable=self.port_var,
            values=["Nema portova"],
            height=38,
            fg_color="#1f2937",
            button_color=COLOR_INFO,
            button_hover_color=COLOR_INFO_HOVER,
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        self.port_menu.grid(row=1, column=0, padx=16, pady=6, sticky="ew")

        ctk.CTkButton(
            self.connection_card,
            text="Osvježi portove",
            height=34,
            fg_color=COLOR_INFO,
            hover_color=COLOR_INFO_HOVER,
            command=self.refresh_ports,
        ).grid(row=2, column=0, padx=16, pady=6, sticky="ew")

        self.connect_btn = ctk.CTkButton(
            self.connection_card,
            text="POVEŽI SISTEM",
            height=42,
            fg_color=COLOR_INFO,
            hover_color=COLOR_INFO_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.connect,
        )
        self.connect_btn.grid(row=3, column=0, padx=16, pady=(14, 6), sticky="ew")

        self.disconnect_btn = ctk.CTkButton(
            self.connection_card,
            text="PREKINI VEZU",
            height=38,
            fg_color=COLOR_INFO,
            hover_color=COLOR_INFO_HOVER,
            command=self.disconnect,
        )
        self.disconnect_btn.grid(row=4, column=0, padx=16, pady=(6, 16), sticky="ew")

        self.hardware_card = ctk.CTkFrame(self.sidebar, corner_radius=20, fg_color=COLOR_SURFACE)
        self.hardware_card.grid(row=3, column=0, padx=20, pady=10, sticky="ew")

        ctk.CTkLabel(
            self.hardware_card,
            text="HARDVER MAPA",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#60a5fa",
        ).pack(anchor="w", padx=16, pady=(16, 8))

        self.hw_canvas = tk.Canvas(
            self.hardware_card,
            width=250,
            height=190,
            bg=COLOR_SURFACE,
            highlightthickness=0,
        )
        self.hw_canvas.pack(padx=8, pady=(0, 8))
        self.draw_hardware_map()

        self.hardware_info = ctk.CTkFrame(self.hardware_card, fg_color=COLOR_SURFACE_2, corner_radius=14)
        self.hardware_info.pack(fill="x", padx=14, pady=(0, 14))

        hardware_text = (
            "Baud rate: 9600\n"
            "Bluetooth: HC-06\n"
            "BT RX/TX: D10/D11\n"
            "Servo 1: D6\n"
            "Servo 2: D5\n"
            "Napajanje: vanjski 5V/6V"
        )

        ctk.CTkLabel(
            self.hardware_info,
            text=hardware_text,
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color="#cbd5e1",
            justify="left",
        ).pack(anchor="w", padx=14, pady=12)

        self.telemetry_card = ctk.CTkFrame(self.sidebar, corner_radius=20, fg_color=COLOR_SURFACE)
        self.telemetry_card.grid(row=4, column=0, padx=20, pady=10, sticky="ew")

        ctk.CTkLabel(
            self.telemetry_card,
            text="INDIKATORI",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#60a5fa",
        ).pack(anchor="w", padx=16, pady=(16, 8))

        self.gauge_canvas = tk.Canvas(
            self.telemetry_card,
            width=250,
            height=145,
            bg=COLOR_SURFACE,
            highlightthickness=0,
        )
        self.gauge_canvas.pack(padx=8, pady=(0, 14))

        self.note = ctk.CTkLabel(
            self.sidebar,
            text="Digital Twin prikazuje očekivano stanje\nna osnovu komandi i Arduino statusa.\nZa realnu silu/struju treba dodatni senzor.",
            font=ctk.CTkFont(size=11),
            text_color="#64748b",
            justify="left",
        )
        self.note.grid(row=9, column=0, padx=24, pady=(4, 14), sticky="sw")

    def build_main(self):
        self.main = ctk.CTkFrame(self, fg_color=COLOR_BG, corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(4, weight=1)

        self.build_status_bar()
        self.build_metrics()
        self.build_controls()
        self.build_mid_panels()
        self.build_log_panel()

    def build_status_bar(self):
        self.topbar = ctk.CTkFrame(self.main, corner_radius=18, fg_color=COLOR_SURFACE_2)
        self.topbar.grid(row=0, column=0, padx=24, pady=(20, 12), sticky="ew")
        self.topbar.grid_columnconfigure(1, weight=1)

        self.status_dot = tk.Canvas(self.topbar, width=22, height=22, bg=COLOR_SURFACE_2, highlightthickness=0)
        self.status_dot.grid(row=0, column=0, padx=(18, 8), pady=16)

        self.system_status = ctk.CTkLabel(
            self.topbar,
            text="OFFLINE",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#ef4444",
        )
        self.system_status.grid(row=0, column=1, sticky="w")

        self.latency_label = ctk.CTkLabel(
            self.topbar,
            text="Latency: — ms",
            font=ctk.CTkFont(family="Consolas", size=14),
            text_color="#cbd5e1",
        )
        self.latency_label.grid(row=0, column=2, padx=14)

        self.com_label = ctk.CTkLabel(
            self.topbar,
            text="COM: —",
            font=ctk.CTkFont(family="Consolas", size=14),
            text_color="#cbd5e1",
        )
        self.com_label.grid(row=0, column=3, padx=(0, 18))

    def build_metrics(self):
        self.metrics = ctk.CTkFrame(self.main, fg_color="transparent")
        self.metrics.grid(row=1, column=0, padx=24, pady=(0, 12), sticky="ew")
        self.metrics.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.metric_command = self.metric_card("Zadnja komanda", "Nema", "#60a5fa")
        self.metric_command.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        self.metric_mode = self.metric_card("Režim rada", "Ručno", "#22c55e")
        self.metric_mode.grid(row=0, column=1, padx=8, sticky="ew")

        self.metric_servo1 = self.metric_card("Servo 1", f"{SERVO1_HOME}°", "#facc15")
        self.metric_servo1.grid(row=0, column=2, padx=8, sticky="ew")

        self.metric_servo2 = self.metric_card("Servo 2", f"{SERVO2_HOME}°", "#facc15")
        self.metric_servo2.grid(row=0, column=3, padx=(8, 0), sticky="ew")

    def build_controls(self):
        self.controls = ctk.CTkFrame(self.main, corner_radius=22, fg_color=COLOR_SURFACE)
        self.controls.grid(row=2, column=0, padx=24, pady=(0, 12), sticky="ew")
        self.controls.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(
            self.controls,
            text="Upravljanje",
            font=ctk.CTkFont(size=19, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, columnspan=4, padx=20, pady=(18, 8), sticky="w")

        self.buttons = []
        self.command_button("UHVATI", "g", "Start sekvence", COLOR_INFO, COLOR_INFO_HOVER, 0)
        self.command_button("E-STOP / PUSTI", "f", "Sigurno zaustavljanje", COLOR_DANGER, COLOR_DANGER_HOVER, 1)
        self.command_button("HOME", "h", "Početni položaj", COLOR_NEUTRAL, COLOR_NEUTRAL_HOVER, 2)
        self.command_button("OTVORI", "o", "Otpuštanje", COLOR_NEUTRAL, COLOR_NEUTRAL_HOVER, 3)
        self.command_button("ZATEGNI", "c", "Finalni grip", COLOR_NEUTRAL, COLOR_NEUTRAL_HOVER, 4)
        self.command_button("TEST S1", "1", "Dijagnostika", COLOR_WARNING, COLOR_WARNING_HOVER, 5)
        self.command_button("TEST S2", "2", "Dijagnostika", COLOR_WARNING, COLOR_WARNING_HOVER, 6)
        self.command_button("PING", "?", "Dijagnostika", COLOR_WARNING, COLOR_WARNING_HOVER, 7)

    def build_mid_panels(self):
        self.mid = ctk.CTkFrame(self.main, fg_color="transparent")
        self.mid.grid(row=3, column=0, padx=24, pady=(0, 12), sticky="ew")
        self.mid.grid_columnconfigure(0, weight=1)
        self.mid.grid_columnconfigure(1, weight=1)

        self.viz_card = ctk.CTkFrame(self.mid, corner_radius=22, fg_color=COLOR_SURFACE)
        self.viz_card.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        self.viz_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.viz_card,
            text="Digital Twin / Wireframe",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=18, pady=(16, 4), sticky="w")

        self.viz_canvas = tk.Canvas(self.viz_card, height=235, bg="#0b1120", highlightthickness=0)
        self.viz_canvas.grid(row=1, column=0, padx=18, pady=(6, 18), sticky="ew")

        self.calib_card = ctk.CTkFrame(self.mid, corner_radius=22, fg_color=COLOR_SURFACE)
        self.calib_card.grid(row=0, column=1, padx=(10, 0), sticky="nsew")
        self.calib_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.calib_card,
            text="Kalibracija pokreta",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=18, pady=(16, 6), sticky="w")

        self.servo1_slider = self.slider_row("Servo 1 ugao", 0, 180, SERVO1_HOME, self.on_servo1_slider)
        self.servo1_slider.grid(row=1, column=0, padx=18, pady=7, sticky="ew")

        self.servo2_slider = self.slider_row("Servo 2 ugao", 0, 180, SERVO2_HOME, self.on_servo2_slider)
        self.servo2_slider.grid(row=2, column=0, padx=18, pady=7, sticky="ew")

        self.speed_frame = ctk.CTkFrame(self.calib_card, fg_color=COLOR_SURFACE_2, corner_radius=16)
        self.speed_frame.grid(row=3, column=0, padx=18, pady=(10, 16), sticky="ew")
        self.speed_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.speed_frame, text="Brzina animacije", text_color="#cbd5e1", font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=0, padx=12, pady=12, sticky="w")
        self.speed_value = ctk.CTkLabel(self.speed_frame, text="100%", font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color="#facc15")
        self.speed_value.grid(row=0, column=2, padx=12, pady=12, sticky="e")
        self.speed_slider = ctk.CTkSlider(self.speed_frame, from_=50, to=150, command=self.on_speed_slider)
        self.speed_slider.set(100)
        self.speed_slider.grid(row=1, column=0, columnspan=3, padx=12, pady=(0, 14), sticky="ew")

    def build_log_panel(self):
        self.bottom = ctk.CTkFrame(self.main, corner_radius=22, fg_color=COLOR_SURFACE)
        self.bottom.grid(row=4, column=0, padx=24, pady=(0, 20), sticky="nsew")
        self.bottom.grid_columnconfigure(0, weight=1)
        self.bottom.grid_rowconfigure(1, weight=1)

        self.log_header = ctk.CTkFrame(self.bottom, fg_color="transparent")
        self.log_header.grid(row=0, column=0, padx=18, pady=(16, 8), sticky="ew")
        self.log_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.log_header,
            text="Napredni komunikacijski log",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        self.filter_var = ctk.StringVar(value="ALL")
        self.filter_menu = ctk.CTkOptionMenu(
            self.log_header,
            variable=self.filter_var,
            values=["ALL", "INFO", "TX", "RX", "WARN", "ERROR", "OK"],
            width=110,
            command=self.change_filter,
        )
        self.filter_menu.grid(row=0, column=1, padx=6)

        self.record_btn = ctk.CTkButton(self.log_header, text="REC MACRO", width=110, fg_color=COLOR_INFO, hover_color=COLOR_INFO_HOVER, command=self.toggle_recording)
        self.record_btn.grid(row=0, column=2, padx=6)

        self.play_btn = ctk.CTkButton(self.log_header, text="PLAY MACRO", width=120, fg_color=COLOR_INFO, hover_color=COLOR_INFO_HOVER, command=self.play_macro)
        self.play_btn.grid(row=0, column=3, padx=6)

        self.export_btn = ctk.CTkButton(self.log_header, text="EXPORT", width=90, fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER, command=self.export_logs)
        self.export_btn.grid(row=0, column=4, padx=6)

        self.clear_btn = ctk.CTkButton(self.log_header, text="CLEAR", width=80, fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER, command=self.clear_log)
        self.clear_btn.grid(row=0, column=5, padx=(6, 0))

        self.log_box = tk.Text(
            self.bottom,
            bg="#020617",
            fg="#d1d5db",
            insertbackground="white",
            relief="flat",
            font=("Consolas", 11),
            padx=12,
            pady=10,
            wrap="word",
        )
        self.log_box.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")
        self.log_box.tag_config("TIME", foreground="#64748b")
        self.log_box.tag_config("INFO", foreground="#93c5fd")
        self.log_box.tag_config("TX", foreground="#60a5fa")
        self.log_box.tag_config("RX", foreground="#22c55e")
        self.log_box.tag_config("WARN", foreground="#facc15")
        self.log_box.tag_config("ERROR", foreground="#f87171")
        self.log_box.tag_config("OK", foreground="#34d399")
        self.log_box.tag_config("MSG", foreground="#e5e7eb")

    def metric_card(self, label, value, color):
        frame = ctk.CTkFrame(self.metrics, corner_radius=18, fg_color=COLOR_SURFACE)
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=label.upper(), font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8").grid(row=0, column=0, padx=16, pady=(14, 2), sticky="w")
        value_label = ctk.CTkLabel(frame, text=value, font=ctk.CTkFont(family="Consolas", size=22, weight="bold"), text_color=color)
        value_label.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="w")
        frame.value_label = value_label
        return frame

    def command_button(self, text, cmd, subtitle, color, hover, idx):
        row = 1 + idx // 4
        col = idx % 4
        frame = ctk.CTkFrame(self.controls, corner_radius=18, fg_color=COLOR_SURFACE_2)
        frame.grid(row=row, column=col, padx=12, pady=10, sticky="ew")
        btn = ctk.CTkButton(frame, text=text, height=48, corner_radius=14, fg_color=color, hover_color=hover, font=ctk.CTkFont(size=14, weight="bold"), command=lambda: self.send_command(cmd, text))
        btn.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkLabel(frame, text=subtitle, font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(pady=(0, 10))
        frame.button = btn
        self.buttons.append(frame)
        return frame

    def slider_row(self, label, from_, to, initial, callback):
        frame = ctk.CTkFrame(self.calib_card, fg_color=COLOR_SURFACE_2, corner_radius=16)
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(frame, text=label, text_color="#cbd5e1", font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=0, padx=12, pady=10, sticky="w")
        value_label = ctk.CTkLabel(frame, text=f"{initial}°", font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color="#facc15")
        value_label.grid(row=0, column=2, padx=12, pady=10, sticky="e")
        slider = ctk.CTkSlider(frame, from_=from_, to=to, command=lambda v: callback(int(v), value_label))
        slider.set(initial)
        slider.grid(row=1, column=0, columnspan=3, padx=12, pady=(0, 12), sticky="ew")
        frame.slider = slider
        frame.value_label = value_label
        return frame

    def draw_hardware_map(self):
        c = self.hw_canvas
        c.delete("all")
        c.create_rectangle(58, 20, 192, 170, outline="#334155", width=2, fill="#0b1120")
        c.create_text(125, 38, text="ARDUINO UNO", fill="#e5e7eb", font=("Consolas", 11, "bold"))
        pins = [
            ("D10 RX", 42, 68, "pin_d10"),
            ("D11 TX", 42, 96, "pin_d11"),
            ("D6 S1", 208, 68, "pin_d6"),
            ("D5 S2", 208, 96, "pin_d5"),
            ("GND", 125, 154, "pin_gnd"),
        ]
        for text, x, y, tag in pins:
            color = "#475569" if tag != "pin_gnd" else "#22c55e"
            c.create_oval(x - 7, y - 7, x + 7, y + 7, fill=color, outline="", tags=tag)
            anchor = "e" if x < 100 else "w" if x > 150 else "center"
            tx = x - 12 if x < 100 else x + 12 if x > 150 else x
            c.create_text(tx, y, text=text, fill="#cbd5e1", anchor=anchor, font=("Consolas", 10))
        c.create_text(125, 188, text="Pinovi svijetle pri aktivnosti", fill="#64748b", font=("Consolas", 9))

    def activate_pin(self, tag, color="#facc15", duration=380):
        self.hw_canvas.itemconfigure(tag, fill=color)
        base = "#22c55e" if tag == "pin_gnd" else "#475569"
        self.after(duration, lambda: self.hw_canvas.itemconfigure(tag, fill=base))

    def redraw_visuals(self):
        self.draw_status_dot()
        self.draw_gauges()
        self.draw_wireframe()
        self.after(160, self.redraw_visuals)

    def draw_status_dot(self):
        self.status_dot.delete("all")
        color = "#22c55e" if self.serial.connected() else "#ef4444"
        self.status_dot.create_oval(4, 4, 18, 18, fill=color, outline="")

    def draw_gauges(self):
        c = self.gauge_canvas
        c.delete("all")
        self.draw_gauge(c, 66, 76, 45, self.grip_intensity, "GRIP", "#22c55e")
        self.draw_gauge(c, 184, 76, 45, 82 if self.serial.connected() else 0, "LINK", "#60a5fa")

    def draw_gauge(self, canvas, cx, cy, r, percent, label, color):
        percent = max(0, min(100, percent))
        canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline="#1f2937", width=10)
        canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=225, extent=-270 * (percent / 100), style="arc", outline=color, width=10)
        canvas.create_text(cx, cy-4, text=f"{int(percent)}%", fill="#f8fafc", font=("Consolas", 13, "bold"))
        canvas.create_text(cx, cy+18, text=label, fill="#94a3b8", font=("Consolas", 9))

    def draw_wireframe(self):
        c = self.viz_canvas
        c.delete("all")
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())
        cx, cy = w // 2, h // 2 + 6
        c.create_oval(cx - 62, cy - 62, cx + 62, cy + 62, outline="#334155", width=2)
        c.create_text(cx, cy, text="GRAPPLER", fill="#e5e7eb", font=("Consolas", 11, "bold"))
        pull_ratio = self.grip_intensity / 100.0
        curl = 22 + 46 * pull_ratio
        color = "#60a5fa" if pull_ratio < 0.45 else "#facc15" if pull_ratio < 0.8 else "#22c55e"
        for i in range(6):
            base_ang = math.radians(i * 60 - 90)
            x0 = cx + math.cos(base_ang) * 74
            y0 = cy + math.sin(base_ang) * 74
            bend = math.radians(curl * math.sin(i + pull_ratio * math.pi))
            x1 = x0 + math.cos(base_ang + bend) * 58
            y1 = y0 + math.sin(base_ang + bend) * 58
            x2 = x1 + math.cos(base_ang + bend * 1.6) * 38
            y2 = y1 + math.sin(base_ang + bend * 1.6) * 38
            c.create_line(x0, y0, x1, y1, fill=color, width=5, capstyle="round")
            c.create_line(x1, y1, x2, y2, fill=color, width=4, capstyle="round")
            c.create_oval(x0 - 5, y0 - 5, x0 + 5, y0 + 5, fill="#0f172a", outline="#94a3b8")
            c.create_oval(x2 - 4, y2 - 4, x2 + 4, y2 + 4, fill=color, outline="")
        c.create_text(18, 18, text=f"Grip intensity: {int(self.grip_intensity)}%", anchor="nw", fill="#cbd5e1", font=("Consolas", 11, "bold"))

    def grip_from_angles(self, s1, s2):
        p1 = (SERVO1_HOME - s1) / max(1, (SERVO1_HOME - SERVO1_PULL))
        p2 = (s2 - SERVO2_HOME) / max(1, (SERVO2_PULL - SERVO2_HOME))
        return max(0, min(100, ((p1 + p2) / 2) * 100))

    def set_visual_angles(self, s1, s2, update_sliders=True):
        self.servo1_angle = int(max(0, min(180, s1)))
        self.servo2_angle = int(max(0, min(180, s2)))
        self.grip_intensity = self.grip_from_angles(self.servo1_angle, self.servo2_angle)
        self.metric_servo1.value_label.configure(text=f"{self.servo1_angle}°")
        self.metric_servo2.value_label.configure(text=f"{self.servo2_angle}°")
        if update_sliders:
            self.updating_sliders = True
            self.servo1_slider.slider.set(self.servo1_angle)
            self.servo2_slider.slider.set(self.servo2_angle)
            self.servo1_slider.value_label.configure(text=f"{self.servo1_angle}°")
            self.servo2_slider.value_label.configure(text=f"{self.servo2_angle}°")
            self.updating_sliders = False

    def cancel_visual_animation(self):
        for handle in self.animation_handles:
            try:
                self.after_cancel(handle)
            except Exception:
                pass
        self.animation_handles.clear()

    def animate_to(self, target1, target2, duration_ms=800, steps=40, delay_offset=0):
        start1 = self.servo1_angle
        start2 = self.servo2_angle
        duration_ms = max(80, int(duration_ms * (100 / max(20, self.speed_slider.get()))))
        steps = max(5, steps)

        def step(k=0):
            t = k / steps
            smooth = t * t * (3 - 2 * t)
            s1 = start1 + (target1 - start1) * smooth
            s2 = start2 + (target2 - start2) * smooth
            self.set_visual_angles(s1, s2)
            if k < steps:
                self.animation_handles.append(self.after(duration_ms // steps, lambda: step(k + 1)))

        self.animation_handles.append(self.after(delay_offset, step))
        return delay_offset + duration_ms

    def start_grasp_visual_sequence(self):
        self.cancel_visual_animation()
        offset = 0
        offset = self.animate_to(SERVO1_PULL, SERVO2_HOME, 850, delay_offset=offset)
        offset = self.animate_to(SERVO1_PULL, SERVO2_PULL, 900, delay_offset=offset + 180)
        offset = self.animate_to(SERVO1_MID, SERVO2_MID, 800, delay_offset=offset + 180)
        self.animate_to(SERVO1_PULL, SERVO2_PULL, 700, delay_offset=offset + 180)

    def refresh_ports(self):
        ports = [p.device for p in list_ports.comports()]
        if ports:
            self.port_menu.configure(values=ports)
            self.port_var.set(DEFAULT_PORT if DEFAULT_PORT in ports else ports[0])
            self.log(f"Pronađeni portovi: {', '.join(ports)}", "INFO")
        else:
            self.port_menu.configure(values=["Nema portova"])
            self.port_var.set("Nema portova")
            self.log("Nema dostupnih COM portova.", "WARN")

    def connect(self):
        port = self.port_var.get()
        if not port or port == "Nema portova":
            messagebox.showwarning("Greška", "Nije izabran COM port.")
            return
        try:
            self.serial.connect(port)
            self.set_connected_ui(True)
            self.log(f"Povezano na {port} pri {BAUD} baud.", "OK")
            self.send_command("h", "Home", record=False)
        except serial.SerialException as e:
            self.log(f"Ne mogu otvoriti {port}: {e}", "ERROR")
            messagebox.showerror("Greška", "Ne mogu otvoriti COM port. Zatvori Arduino Serial Monitor, PuTTY ili drugi program koji koristi isti port.")

    def disconnect(self):
        was_connected = self.serial.connected()
        self.serial.disconnect()
        self.set_connected_ui(False)
        if was_connected:
            self.log("Konekcija je prekinuta.", "INFO")

    def set_connected_ui(self, connected):
        state = "normal" if connected else "disabled"
        for b in self.buttons:
            b.button.configure(state=state)
        self.disconnect_btn.configure(state=state)
        self.connect_btn.configure(state="disabled" if connected else "normal")
        self.system_status.configure(text="ONLINE" if connected else "OFFLINE", text_color="#22c55e" if connected else "#ef4444")
        self.com_label.configure(text=f"COM: {self.serial.port if connected else '—'}")
        self.metric_mode.value_label.configure(text="Spreman" if connected else "Ručno", text_color="#22c55e" if connected else "#94a3b8")

    def send_command(self, cmd, description, record=True):
        if not self.serial.connected():
            self.log("Komanda nije poslana jer sistem nije povezan.", "WARN")
            return
        try:
            self.serial.write(cmd)
            self.metric_command.value_label.configure(text=description, text_color="#60a5fa")
            self.metric_mode.value_label.configure(text="Aktivno", text_color="#facc15")
            self.log(f"{description}  →  '{cmd.strip()}'", "TX")

            if cmd == "g":
                self.start_grasp_visual_sequence()
            elif cmd in ("f", "h", "o"):
                self.cancel_visual_animation()
                self.animate_to(SERVO1_HOME, SERVO2_HOME, 650)
            elif cmd == "c":
                self.cancel_visual_animation()
                self.animate_to(SERVO1_PULL, SERVO2_PULL, 700)
            elif cmd == "1":
                self.cancel_visual_animation()
                self.animate_to(SERVO1_PULL, self.servo2_angle, 420)
                self.animate_to(SERVO1_HOME, self.servo2_angle, 420, delay_offset=520)
            elif cmd == "2":
                self.cancel_visual_animation()
                self.animate_to(self.servo1_angle, SERVO2_PULL, 420)
                self.animate_to(self.servo1_angle, SERVO2_HOME, 420, delay_offset=520)
            elif cmd == "?":
                self.pending_ping = time.perf_counter()

            if not (cmd.startswith("A") or cmd.startswith("B")):
                self.flash_pins_for_cmd(cmd)

            if record and self.recording:
                self.macro_events.append({"t": time.perf_counter() - self.record_start, "cmd": cmd, "description": description})
        except serial.SerialException as e:
            self.log(f"Greška pri slanju: {e}", "ERROR")
            self.disconnect()

    def flash_pins_for_cmd(self, cmd):
        self.activate_pin("pin_d11", "#60a5fa")
        if cmd in ("1", "g", "c"):
            self.activate_pin("pin_d6", "#facc15")
        if cmd in ("2", "g", "o"):
            self.activate_pin("pin_d5", "#facc15")
        if cmd == "?":
            self.activate_pin("pin_d10", "#22c55e")

    def auto_read(self):
        try:
            for line in self.serial.read_lines():
                self.log(f"Arduino: {line}", "RX")
                self.activate_pin("pin_d10", "#22c55e")
                self.handle_arduino_line(line)
        except serial.SerialException as e:
            self.log(f"Greška pri čitanju: {e}", "ERROR")
            self.disconnect()
        self.after(120, self.auto_read)

    def handle_arduino_line(self, line):
        upper = line.upper()
        if self.pending_ping is not None:
            self.latency_label.configure(text=f"Latency: {int((time.perf_counter() - self.pending_ping) * 1000)} ms")
            self.pending_ping = None
        if "HOME" in upper or "OPEN" in upper or "STOP" in upper:
            self.metric_mode.value_label.configure(text="Sigurno", text_color="#22c55e")
        elif "START" in upper or "FAZA" in upper:
            self.metric_mode.value_label.configure(text="Aktivno", text_color="#facc15")
        elif "DRZI" in upper:
            self.metric_mode.value_label.configure(text="Drži objekat", text_color="#22c55e")
            self.set_visual_angles(SERVO1_PULL, SERVO2_PULL)

    def on_servo1_slider(self, value, label):
        if self.updating_sliders:
            return
        self.cancel_visual_animation()
        self.set_visual_angles(value, self.servo2_angle, update_sliders=False)
        label.configure(text=f"{int(value)}°")
        if self.serial.connected():
            self.send_command(f"A{int(value):03d}\n", f"Servo 1 = {int(value)}°", record=False)

    def on_servo2_slider(self, value, label):
        if self.updating_sliders:
            return
        self.cancel_visual_animation()
        self.set_visual_angles(self.servo1_angle, value, update_sliders=False)
        label.configure(text=f"{int(value)}°")
        if self.serial.connected():
            self.send_command(f"B{int(value):03d}\n", f"Servo 2 = {int(value)}°", record=False)

    def on_speed_slider(self, value):
        self.speed_value.configure(text=f"{int(value)}%")

    def toggle_recording(self):
        if not self.recording:
            self.recording = True
            self.macro_events.clear()
            self.record_start = time.perf_counter()
            self.record_btn.configure(text="STOP REC", fg_color=COLOR_DANGER, hover_color=COLOR_DANGER_HOVER)
            self.log("Macro recorder pokrenut.", "OK")
        else:
            self.recording = False
            self.record_btn.configure(text="REC MACRO", fg_color=COLOR_INFO, hover_color=COLOR_INFO_HOVER)
            self.log(f"Macro snimljen: {len(self.macro_events)} komandi.", "OK")

    def play_macro(self):
        if not self.macro_events:
            self.log("Nema snimljenog macro niza.", "WARN")
            return
        self.log("Reprodukcija macro niza pokrenuta.", "OK")
        start = time.perf_counter()
        for event in self.macro_events:
            delay_ms = max(0, int((event["t"] - (time.perf_counter() - start)) * 1000))
            self.after(delay_ms, lambda e=event: self.send_command(e["cmd"], f"Macro: {e['description']}", record=False))

    def log(self, message, level="INFO"):
        entry = {"time": datetime.now().strftime("%H:%M:%S"), "level": level, "message": message}
        self.logs.append(entry)
        if self.log_filter == "ALL" or self.log_filter == level:
            self.insert_log(entry)

    def insert_log(self, entry):
        self.log_box.insert("end", "[", "TIME")
        self.log_box.insert("end", entry["time"], "TIME")
        self.log_box.insert("end", "] [", "TIME")
        self.log_box.insert("end", entry["level"], entry["level"] if entry["level"] in ["INFO", "TX", "RX", "WARN", "ERROR", "OK"] else "INFO")
        self.log_box.insert("end", "] ", "TIME")
        self.log_box.insert("end", entry["message"] + "\n", "MSG")
        self.log_box.see("end")

    def change_filter(self, value):
        self.log_filter = value
        self.log_box.delete("1.0", "end")
        for entry in self.logs:
            if value == "ALL" or entry["level"] == value:
                self.insert_log(entry)

    def clear_log(self):
        self.logs.clear()
        self.log_box.delete("1.0", "end")
        self.log("Log očišćen.", "INFO")

    def export_logs(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV file", "*.csv"), ("JSON file", "*.json")])
        if not path:
            return
        try:
            if path.lower().endswith(".json"):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.logs, f, indent=2, ensure_ascii=False)
            else:
                with open(path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=["time", "level", "message"])
                    writer.writeheader()
                    writer.writerows(self.logs)
            self.log(f"Log exportovan: {path}", "OK")
        except OSError as e:
            self.log(f"Export greška: {e}", "ERROR")

    def on_close(self):
        self.disconnect()
        self.destroy()


if __name__ == "__main__":
    app = GrapplerUltraApp()
    app.mainloop()
