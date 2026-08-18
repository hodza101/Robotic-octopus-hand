import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import serial
from serial.tools import list_ports
from datetime import datetime
from collections import deque
import time
import math
import json
import csv
import random

# ============================================================
#  SPIROB GRAPPLER CONTROL PANEL - PRO VERSION
#  HC-06 Bluetooth / Arduino Uno / Servo control
# ============================================================

BAUD = 9600
DEFAULT_PORT = "COM4"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class SerialManager:
    def __init__(self):
        self.ser = None
        self.port = None

    def connect(self, port: str):
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

    def is_connected(self):
        return self.ser is not None and self.ser.is_open

    def write(self, data: str):
        if not self.is_connected():
            raise serial.SerialException("Serial port nije povezan")
        self.ser.write(data.encode("ascii", errors="ignore"))
        self.ser.flush()

    def read_lines(self):
        if not self.is_connected():
            return []
        lines = []
        try:
            while self.ser.in_waiting:
                line = self.ser.readline().decode(errors="ignore").strip()
                if line:
                    lines.append(line)
        except serial.SerialException:
            raise
        return lines


class GrapplerProApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SpiRob Grappler Mission Control")
        self.geometry("1280x780")
        self.minsize(1120, 700)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.serial = SerialManager()
        self.logs = []
        self.log_filter = "ALL"
        self.recording = False
        self.macro_events = []
        self.record_start = None
        self.pending_ping = None
        self.last_latency_ms = None
        self.command_active_until = 0
        self.servo1_angle = 180
        self.servo2_angle = 0
        self.battery_voltage = 5.05
        self.rssi_percent = 82
        self.graph_current = deque([0.18] * 160, maxlen=160)
        self.graph_servo1 = deque([180] * 160, maxlen=160)
        self.graph_servo2 = deque([0] * 160, maxlen=160)

        self.configure(bg="#070b14")
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.build_sidebar()
        self.build_main()
        self.refresh_ports()
        self.set_connected_ui(False)
        self.log("Aplikacija pokrenuta. Izaberi COM port i poveži HC-06.", "INFO")

        self.after(120, self.auto_read)
        self.after(150, self.update_visuals)
        self.after(5000, self.auto_ping)

    # ========================================================
    # UI BUILD
    # ========================================================

    def build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=310, corner_radius=0, fg_color="#0b1220")
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(10, weight=1)

        self.logo = ctk.CTkLabel(
            self.sidebar,
            text="SPIROB\nMISSION CONTROL",
            font=ctk.CTkFont(size=27, weight="bold"),
            text_color="#f8fafc",
            justify="left",
        )
        self.logo.grid(row=0, column=0, padx=26, pady=(26, 4), sticky="w")

        self.tagline = ctk.CTkLabel(
            self.sidebar,
            text="Industrial Bluetooth Interface\nHC-06 • Arduino Uno • Servo Drive",
            font=ctk.CTkFont(size=13),
            text_color="#94a3b8",
            justify="left",
        )
        self.tagline.grid(row=1, column=0, padx=26, pady=(0, 22), sticky="w")

        self.connection_card = ctk.CTkFrame(self.sidebar, corner_radius=20, fg_color="#111827")
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
            button_color="#2563eb",
            button_hover_color="#1d4ed8",
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        self.port_menu.grid(row=1, column=0, padx=16, pady=6, sticky="ew")

        self.refresh_btn = ctk.CTkButton(
            self.connection_card,
            text="Osvježi portove",
            height=34,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.refresh_ports,
        )
        self.refresh_btn.grid(row=2, column=0, padx=16, pady=6, sticky="ew")

        self.connect_btn = ctk.CTkButton(
            self.connection_card,
            text="POVEŽI SISTEM",
            height=42,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.connect,
        )
        self.connect_btn.grid(row=3, column=0, padx=16, pady=(14, 6), sticky="ew")

        self.disconnect_btn = ctk.CTkButton(
            self.connection_card,
            text="PREKINI VEZU",
            height=38,
            fg_color="#7f1d1d",
            hover_color="#991b1b",
            command=self.disconnect,
        )
        self.disconnect_btn.grid(row=4, column=0, padx=16, pady=(6, 16), sticky="ew")

        self.hardware_card = ctk.CTkFrame(self.sidebar, corner_radius=20, fg_color="#111827")
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
            bg="#111827",
            highlightthickness=0,
        )
        self.hw_canvas.pack(padx=8, pady=(0, 12))
        self.draw_hardware_map()

        self.telemetry_card = ctk.CTkFrame(self.sidebar, corner_radius=20, fg_color="#111827")
        self.telemetry_card.grid(row=4, column=0, padx=20, pady=10, sticky="ew")

        ctk.CTkLabel(
            self.telemetry_card,
            text="TELEMETRIJA",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#60a5fa",
        ).pack(anchor="w", padx=16, pady=(16, 8))

        self.gauge_canvas = tk.Canvas(
            self.telemetry_card,
            width=250,
            height=145,
            bg="#111827",
            highlightthickness=0,
        )
        self.gauge_canvas.pack(padx=8, pady=(0, 14))

        self.note = ctk.CTkLabel(
            self.sidebar,
            text="Napomena: graf struje/RSSI je UI telemetrija.\nZa realne vrijednosti treba senzor struje\nili Arduino telemetrijski protokol.",
            font=ctk.CTkFont(size=11),
            text_color="#64748b",
            justify="left",
        )
        self.note.grid(row=9, column=0, padx=24, pady=(4, 14), sticky="sw")

    def build_main(self):
        self.main = ctk.CTkFrame(self, fg_color="#070b14", corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(4, weight=1)

        self.build_top_bar()
        self.build_metrics()
        self.build_controls()
        self.build_mid_panels()
        self.build_log_panel()

    def build_top_bar(self):
        self.topbar = ctk.CTkFrame(self.main, corner_radius=18, fg_color="#0f172a")
        self.topbar.grid(row=0, column=0, padx=24, pady=(20, 12), sticky="ew")
        self.topbar.grid_columnconfigure(1, weight=1)

        self.status_dot = tk.Canvas(self.topbar, width=22, height=22, bg="#0f172a", highlightthickness=0)
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

        self.metric_servo1 = self.metric_card("Servo 1", "180°", "#facc15")
        self.metric_servo1.grid(row=0, column=2, padx=8, sticky="ew")

        self.metric_servo2 = self.metric_card("Servo 2", "0°", "#facc15")
        self.metric_servo2.grid(row=0, column=3, padx=(8, 0), sticky="ew")

    def build_controls(self):
        self.controls = ctk.CTkFrame(self.main, corner_radius=22, fg_color="#111827")
        self.controls.grid(row=2, column=0, padx=24, pady=(0, 12), sticky="ew")
        self.controls.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(
            self.controls,
            text="Upravljanje",
            font=ctk.CTkFont(size=19, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, columnspan=4, padx=20, pady=(18, 8), sticky="w")

        self.buttons = []

        self.btn_grab = self.command_button("UHVATI", "g", "Start sekvence", "#2563eb", "#1d4ed8", 0)
        self.btn_stop = self.command_button("E-STOP / PUSTI", "f", "Sigurno zaustavljanje", "#dc2626", "#b91c1c", 1)
        self.btn_home = self.command_button("HOME", "h", "Početni položaj", "#334155", "#475569", 2)
        self.btn_open = self.command_button("OTVORI", "o", "Otpuštanje", "#0f766e", "#115e59", 3)

        self.btn_close = self.command_button("ZATEGNI", "c", "Finalni grip", "#7c3aed", "#6d28d9", 4)
        self.btn_t1 = self.command_button("TEST S1", "1", "Servo 1", "#1f2937", "#374151", 5)
        self.btn_t2 = self.command_button("TEST S2", "2", "Servo 2", "#1f2937", "#374151", 6)
        self.btn_ping = self.command_button("PING", "?", "Latency test", "#1f2937", "#374151", 7)

        for i in range(4):
            self.controls.grid_columnconfigure(i, weight=1)

    def build_mid_panels(self):
        self.mid = ctk.CTkFrame(self.main, fg_color="transparent")
        self.mid.grid(row=3, column=0, padx=24, pady=(0, 12), sticky="ew")
        self.mid.grid_columnconfigure(0, weight=1)
        self.mid.grid_columnconfigure(1, weight=1)

        self.viz_card = ctk.CTkFrame(self.mid, corner_radius=22, fg_color="#111827")
        self.viz_card.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        self.viz_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.viz_card,
            text="Digital Twin / Wireframe",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=18, pady=(16, 4), sticky="w")

        self.viz_canvas = tk.Canvas(self.viz_card, height=235, bg="#0b1120", highlightthickness=0)
        self.viz_canvas.grid(row=1, column=0, padx=18, pady=(6, 18), sticky="ew")

        self.tuning_card = ctk.CTkFrame(self.mid, corner_radius=22, fg_color="#111827")
        self.tuning_card.grid(row=0, column=1, padx=(10, 0), sticky="nsew")
        self.tuning_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.tuning_card,
            text="Kalibracija i PID panel",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=18, pady=(16, 6), sticky="w")

        self.servo1_slider = self.slider_row("Servo 1 ugao", 0, 180, 180, self.on_servo1_slider)
        self.servo1_slider.grid(row=1, column=0, padx=18, pady=4, sticky="ew")

        self.servo2_slider = self.slider_row("Servo 2 ugao", 0, 180, 0, self.on_servo2_slider)
        self.servo2_slider.grid(row=2, column=0, padx=18, pady=4, sticky="ew")

        self.pid_frame = ctk.CTkFrame(self.tuning_card, fg_color="#0f172a", corner_radius=16)
        self.pid_frame.grid(row=3, column=0, padx=18, pady=(12, 16), sticky="ew")
        self.pid_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.kp = ctk.StringVar(value="1.00")
        self.ki = ctk.StringVar(value="0.00")
        self.kd = ctk.StringVar(value="0.05")

        self.pid_entry("Kp", self.kp, 0)
        self.pid_entry("Ki", self.ki, 1)
        self.pid_entry("Kd", self.kd, 2)

        self.apply_pid_btn = ctk.CTkButton(
            self.pid_frame,
            text="APPLY PID",
            height=36,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self.apply_pid,
        )
        self.apply_pid_btn.grid(row=0, column=3, padx=8, pady=12, sticky="ew")

    def build_log_panel(self):
        self.bottom = ctk.CTkFrame(self.main, corner_radius=22, fg_color="#111827")
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

        self.record_btn = ctk.CTkButton(
            self.log_header,
            text="REC MACRO",
            width=110,
            fg_color="#7c3aed",
            hover_color="#6d28d9",
            command=self.toggle_recording,
        )
        self.record_btn.grid(row=0, column=2, padx=6)

        self.play_btn = ctk.CTkButton(
            self.log_header,
            text="PLAY MACRO",
            width=120,
            fg_color="#0f766e",
            hover_color="#115e59",
            command=self.play_macro,
        )
        self.play_btn.grid(row=0, column=3, padx=6)

        self.export_btn = ctk.CTkButton(
            self.log_header,
            text="EXPORT",
            width=90,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.export_logs,
        )
        self.export_btn.grid(row=0, column=4, padx=6)

        self.clear_btn = ctk.CTkButton(
            self.log_header,
            text="CLEAR",
            width=80,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.clear_log,
        )
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

    # ========================================================
    # UI HELPERS
    # ========================================================

    def metric_card(self, label, value, color):
        frame = ctk.CTkFrame(self.metrics, corner_radius=18, fg_color="#111827")
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text=label.upper(),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8",
        ).grid(row=0, column=0, padx=16, pady=(14, 2), sticky="w")

        val = ctk.CTkLabel(
            frame,
            text=value,
            font=ctk.CTkFont(family="Consolas", size=22, weight="bold"),
            text_color=color,
        )
        val.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="w")
        frame.value_label = val
        return frame

    def command_button(self, text, cmd, subtitle, color, hover, idx):
        row = 1 + idx // 4
        col = idx % 4
        frame = ctk.CTkFrame(self.controls, corner_radius=18, fg_color="#0f172a")
        frame.grid(row=row, column=col, padx=12, pady=10, sticky="ew")

        btn = ctk.CTkButton(
            frame,
            text=text,
            height=48,
            corner_radius=14,
            fg_color=color,
            hover_color=hover,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=lambda: self.send_command(cmd, text),
        )
        btn.pack(fill="x", padx=12, pady=(12, 4))

        ctk.CTkLabel(
            frame,
            text=subtitle,
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
        ).pack(pady=(0, 10))

        frame.button = btn
        self.buttons.append(frame)
        return frame

    def slider_row(self, label, from_, to, initial, callback):
        frame = ctk.CTkFrame(self.tuning_card, fg_color="#0f172a", corner_radius=16)
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

    def pid_entry(self, label, var, col):
        sub = ctk.CTkFrame(self.pid_frame, fg_color="transparent")
        sub.grid(row=0, column=col, padx=8, pady=10, sticky="ew")
        ctk.CTkLabel(sub, text=label, text_color="#94a3b8", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        ctk.CTkEntry(sub, textvariable=var, height=34, font=ctk.CTkFont(family="Consolas", size=13)).pack(fill="x", pady=(4, 0))

    # ========================================================
    # HARDWARE / VISUALS
    # ========================================================

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
        c.create_text(125, 188, text="Pinovi svijetle kada se koriste", fill="#64748b", font=("Consolas", 9))

    def activate_pin(self, tag, color="#facc15", duration=400):
        self.hw_canvas.itemconfigure(tag, fill=color)
        self.after(duration, lambda: self.hw_canvas.itemconfigure(tag, fill="#475569" if tag != "pin_gnd" else "#22c55e"))

    def draw_gauges(self):
        c = self.gauge_canvas
        c.delete("all")
        self.draw_gauge(c, 66, 76, 45, 4.5, 5.3, self.battery_voltage, "VOLT", "#22c55e")
        self.draw_gauge(c, 184, 76, 45, 0, 100, self.rssi_percent, "RSSI", "#60a5fa")

    def draw_gauge(self, canvas, cx, cy, r, minv, maxv, val, label, color):
        canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline="#1f2937", width=10)
        ratio = max(0, min(1, (val - minv) / (maxv - minv)))
        extent = -270 * ratio
        canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=225, extent=extent, style="arc", outline=color, width=10)
        text_val = f"{val:.2f}V" if label == "VOLT" else f"{int(val)}%"
        canvas.create_text(cx, cy-4, text=text_val, fill="#f8fafc", font=("Consolas", 13, "bold"))
        canvas.create_text(cx, cy+18, text=label, fill="#94a3b8", font=("Consolas", 9))

    def draw_wireframe(self):
        c = self.viz_canvas
        c.delete("all")
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())
        cx, cy = w // 2, h // 2

        c.create_oval(cx-62, cy-62, cx+62, cy+62, outline="#334155", width=2)
        c.create_text(cx, cy, text="GRAPPLER", fill="#e5e7eb", font=("Consolas", 11, "bold"))

        pull_ratio = (abs(self.servo1_angle - 180) + abs(self.servo2_angle - 0)) / 360.0
        pull_ratio = max(0, min(1, pull_ratio))
        curl = 28 + 38 * pull_ratio

        for i in range(6):
            base_ang = math.radians(i * 60 - 90)
            x0 = cx + math.cos(base_ang) * 74
            y0 = cy + math.sin(base_ang) * 74
            bend = math.radians(curl * math.sin(i + pull_ratio * math.pi))
            x1 = x0 + math.cos(base_ang + bend) * 58
            y1 = y0 + math.sin(base_ang + bend) * 58
            x2 = x1 + math.cos(base_ang + bend * 1.6) * 38
            y2 = y1 + math.sin(base_ang + bend * 1.6) * 38

            color = "#60a5fa" if pull_ratio < 0.45 else "#facc15" if pull_ratio < 0.8 else "#22c55e"
            c.create_line(x0, y0, x1, y1, fill=color, width=5, capstyle="round")
            c.create_line(x1, y1, x2, y2, fill=color, width=4, capstyle="round")
            c.create_oval(x0-5, y0-5, x0+5, y0+5, fill="#0f172a", outline="#94a3b8")
            c.create_oval(x2-4, y2-4, x2+4, y2+4, fill=color, outline="")

        c.create_text(18, 18, text=f"S1={self.servo1_angle}°  S2={self.servo2_angle}°", anchor="nw", fill="#cbd5e1", font=("Consolas", 11))
        c.create_text(18, 38, text=f"Grip intensity: {int(pull_ratio * 100)}%", anchor="nw", fill="#94a3b8", font=("Consolas", 10))

    def draw_graph(self):
        # Graph is drawn inside lower part of viz canvas for compactness if width allows.
        # Current graph is synthetic unless Arduino sends real telemetry.
        pass

    def update_visuals(self):
        active = time.time() < self.command_active_until
        synthetic_current = 0.18 + (0.55 if active else 0.0) + random.uniform(-0.04, 0.04)
        synthetic_current += (abs(self.servo1_angle - 90) + abs(self.servo2_angle - 90)) / 900.0
        self.graph_current.append(max(0.05, synthetic_current))
        self.graph_servo1.append(self.servo1_angle)
        self.graph_servo2.append(self.servo2_angle)

        # battery/RSSI simulated smoothing
        self.battery_voltage = max(4.55, min(5.20, self.battery_voltage + random.uniform(-0.01, 0.008)))
        self.rssi_percent = max(55, min(98, self.rssi_percent + random.randint(-1, 1)))

        self.draw_gauges()
        self.draw_wireframe()
        self.draw_status_dot()
        self.after(180, self.update_visuals)

    def draw_status_dot(self):
        self.status_dot.delete("all")
        color = "#22c55e" if self.serial.is_connected() else "#ef4444"
        self.status_dot.create_oval(4, 4, 18, 18, fill=color, outline="")

    # ========================================================
    # SERIAL / LOGIC
    # ========================================================

    def refresh_ports(self):
        ports = [p.device for p in list_ports.comports()]
        if ports:
            self.port_menu.configure(values=ports)
            if DEFAULT_PORT in ports:
                self.port_var.set(DEFAULT_PORT)
            else:
                self.port_var.set(ports[0])
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
        was_connected = self.serial.is_connected()
        self.serial.disconnect()
        self.set_connected_ui(False)
        if was_connected:
            self.log("Konekcija je prekinuta.", "INFO")

    def set_connected_ui(self, connected):
        state = "normal" if connected else "disabled"
        for b in self.buttons:
            if hasattr(b, "button"):
                b.button.configure(state=state)
            else:
                b.configure(state=state)
        self.disconnect_btn.configure(state=state)
        self.connect_btn.configure(state="disabled" if connected else "normal")
        self.system_status.configure(text="ONLINE" if connected else "OFFLINE", text_color="#22c55e" if connected else "#ef4444")
        self.com_label.configure(text=f"COM: {self.serial.port if connected else '—'}")
        self.metric_mode.value_label.configure(text="Spreman" if connected else "Ručno", text_color="#22c55e" if connected else "#94a3b8")

    def send_command(self, cmd, description, record=True):
        if not self.serial.is_connected():
            self.log("Komanda nije poslana jer sistem nije povezan.", "WARN")
            return
        try:
            self.serial.write(cmd)
            self.command_active_until = time.time() + 1.2
            self.metric_command.value_label.configure(text=description, text_color="#60a5fa")
            self.metric_mode.value_label.configure(text="Aktivno", text_color="#facc15")
            self.log(f"{description}  →  '{cmd}'", "TX")

            if cmd == "?":
                self.pending_ping = time.perf_counter()

            if record and self.recording:
                delta = time.perf_counter() - self.record_start
                self.macro_events.append({"t": delta, "cmd": cmd, "description": description})

            self.flash_pins_for_cmd(cmd)
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

    def read_response(self):
        try:
            for line in self.serial.read_lines():
                self.log(f"Arduino: {line}", "RX")
                self.activate_pin("pin_d10", "#22c55e")

                if self.pending_ping is not None:
                    self.last_latency_ms = int((time.perf_counter() - self.pending_ping) * 1000)
                    self.pending_ping = None
                    self.latency_label.configure(text=f"Latency: {self.last_latency_ms} ms")

                self.handle_arduino_line(line)
        except serial.SerialException as e:
            self.log(f"Greška pri čitanju: {e}", "ERROR")
            self.disconnect()

    def handle_arduino_line(self, line):
        u = line.upper()
        if "STOP" in u:
            self.metric_mode.value_label.configure(text="Sigurno", text_color="#22c55e")
        elif "HOME" in u:
            self.metric_mode.value_label.configure(text="Home", text_color="#22c55e")
            self.set_servo_angles(180, 0, send=False)
        elif "START" in u or "FAZA" in u:
            self.metric_mode.value_label.configure(text="Aktivno", text_color="#facc15")
        elif "DRZI" in u or "OBJEKAT" in u:
            self.metric_mode.value_label.configure(text="Drži objekat", text_color="#22c55e")

    def auto_read(self):
        self.read_response()
        self.after(120, self.auto_read)

    def auto_ping(self):
        if self.serial.is_connected():
            self.send_command("?", "Ping", record=False)
        self.after(5000, self.auto_ping)

    # ========================================================
    # SLIDERS / PID / MACROS
    # ========================================================

    def set_servo_angles(self, s1, s2, send=False):
        self.servo1_angle = int(s1)
        self.servo2_angle = int(s2)
        self.metric_servo1.value_label.configure(text=f"{self.servo1_angle}°")
        self.metric_servo2.value_label.configure(text=f"{self.servo2_angle}°")
        if send:
            self.send_command(f"A{self.servo1_angle:03d}\n", f"Servo 1 = {self.servo1_angle}°")
            self.send_command(f"B{self.servo2_angle:03d}\n", f"Servo 2 = {self.servo2_angle}°")

    def on_servo1_slider(self, value, label):
        self.servo1_angle = int(value)
        label.configure(text=f"{self.servo1_angle}°")
        self.metric_servo1.value_label.configure(text=f"{self.servo1_angle}°")
        # Za stvarno pomjeranje Arduino mora podržati komandu A090\n.
        if self.serial.is_connected():
            self.send_command(f"A{self.servo1_angle:03d}\n", f"Servo 1 = {self.servo1_angle}°", record=False)

    def on_servo2_slider(self, value, label):
        self.servo2_angle = int(value)
        label.configure(text=f"{self.servo2_angle}°")
        self.metric_servo2.value_label.configure(text=f"{self.servo2_angle}°")
        # Za stvarno pomjeranje Arduino mora podržati komandu B090\n.
        if self.serial.is_connected():
            self.send_command(f"B{self.servo2_angle:03d}\n", f"Servo 2 = {self.servo2_angle}°", record=False)

    def apply_pid(self):
        try:
            kp = float(self.kp.get())
            ki = float(self.ki.get())
            kd = float(self.kd.get())
        except ValueError:
            self.log("PID vrijednosti moraju biti brojevi.", "ERROR")
            return
        self.send_command(f"P{kp:.3f},{ki:.3f},{kd:.3f}\n", f"PID Kp={kp:.3f}, Ki={ki:.3f}, Kd={kd:.3f}")

    def toggle_recording(self):
        if not self.recording:
            self.recording = True
            self.macro_events.clear()
            self.record_start = time.perf_counter()
            self.record_btn.configure(text="STOP REC", fg_color="#dc2626", hover_color="#b91c1c")
            self.log("Macro recorder pokrenut.", "OK")
        else:
            self.recording = False
            self.record_btn.configure(text="REC MACRO", fg_color="#7c3aed", hover_color="#6d28d9")
            self.log(f"Macro snimljen: {len(self.macro_events)} komandi.", "OK")

    def play_macro(self):
        if not self.macro_events:
            self.log("Nema snimljenog macro niza.", "WARN")
            return
        self.log("Reprodukcija macro niza pokrenuta.", "OK")
        self.metric_mode.value_label.configure(text="Macro", text_color="#7c3aed")
        start = time.perf_counter()
        for event in self.macro_events:
            delay_ms = max(0, int((event["t"] - (time.perf_counter() - start)) * 1000))
            self.after(delay_ms, lambda e=event: self.send_command(e["cmd"], f"Macro: {e['description']}", record=False))

    # ========================================================
    # LOGGING / EXPORT
    # ========================================================

    def log(self, msg, level="INFO"):
        now = datetime.now().strftime("%H:%M:%S")
        entry = {"time": now, "level": level, "message": msg}
        self.logs.append(entry)
        if self.log_filter != "ALL" and self.log_filter != level:
            return
        self.insert_log_entry(entry)

    def insert_log_entry(self, entry):
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
                self.insert_log_entry(entry)

    def clear_log(self):
        self.logs.clear()
        self.log_box.delete("1.0", "end")
        self.log("Log očišćen.", "INFO")

    def export_logs(self):
        if not self.logs:
            self.log("Nema logova za export.", "WARN")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV file", "*.csv"), ("JSON file", "*.json")],
            title="Sačuvaj log"
        )
        if not path:
            return
        try:
            if path.lower().endswith(".json"):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.logs, f, indent=2, ensure_ascii=False)
            else:
                with open(path, "w", newline="", encoding="utf-8") as f:
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
    app = GrapplerProApp()
    app.mainloop()
