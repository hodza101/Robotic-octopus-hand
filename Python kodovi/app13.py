import json
import math
import threading
import time
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
import serial
from serial.tools import list_ports

APP_TITLE = "SpiRob Grappler Mission Control"
BAUD = 9600

CONFIG_FILE = Path("spirob_desktop_config.json")
EXPORT_LOG_FILE = Path("spirob_log_export.json")

SERVO1_HOME = 175
SERVO2_HOME = 5
SERVO1_GRIP = 5
SERVO2_GRIP = 175

COLORS = {
    "bg": "#060a13",
    "sidebar": "#080d18",
    "card": "#111827",
    "card_dark": "#0b1220",
    "card_soft": "#162236",
    "border": "#26364d",
    "text": "#f8fafc",
    "muted": "#94a3b8",
    "blue": "#2563eb",
    "blue_soft": "#1d4ed8",
    "red": "#dc2626",
    "red_soft": "#ef4444",
    "amber": "#f59e0b",
    "green": "#22c55e",
    "slate": "#334155",
    "console": "#020617",
}


def timestamp():
    return datetime.now().strftime("%H:%M:%S")


class RingGauge(ctk.CTkFrame):
    def __init__(self, parent, title, color, size=86):
        super().__init__(parent, fg_color="transparent", width=size, height=size + 24)
        self.size = size
        self.title = title
        self.color = color
        self.value = 0
        self.pack_propagate(False)

        self.canvas = ctk.CTkCanvas(
            self,
            width=size,
            height=size + 24,
            bg=COLORS["card"],
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)
        self.set_value(0)

    def set_value(self, value):
        self.value = max(0, min(100, int(value)))
        c = self.canvas
        c.delete("all")

        s = self.size
        cx = s // 2
        cy = s // 2
        r = s // 2 - 10

        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#1f2937", width=9)
        if self.value > 0:
            c.create_arc(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                start=90,
                extent=-359 * self.value / 100,
                style="arc",
                outline=self.color,
                width=9,
            )

        c.create_text(cx, cy - 4, text=f"{self.value}%", fill="white", font=("Consolas", 14, "bold"))
        c.create_text(cx, cy + 16, text=self.title, fill=COLORS["muted"], font=("Consolas", 10, "bold"))
        c.create_text(
            cx,
            s + 12,
            text="ACTIVE" if self.value else "IDLE",
            fill=self.color if self.value else COLORS["muted"],
            font=("Consolas", 8, "bold"),
        )


class SpiRobDesktopApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(APP_TITLE)
        self.geometry("1560x900")
        self.minsize(1240, 760)
        self.configure(fg_color=COLORS["bg"])

        self.ser = None
        self.reader_running = False
        self.reader_thread = None
        self.connected = False

        self.selected_port = ctk.StringVar(value="-")
        self.live_calibration = ctk.BooleanVar(value=False)

        self.s1 = SERVO1_HOME
        self.s2 = SERVO2_HOME
        self.grip = 0
        self.last_command = "Nema"
        self.last_ack_time = None

        self.logs = []
        self.macro = []
        self.recording = False

        self.live_job_s1 = None
        self.live_job_s2 = None

        self.load_config()
        self.build_layout()
        self.refresh_ports()
        self.refresh_ui()
        self.after(250, self.draw_digital_twin)

    # ------------------------- CONFIG -------------------------

    def load_config(self):
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                self.selected_port.set(data.get("port", "-"))
                self.s1 = int(data.get("s1", self.s1))
                self.s2 = int(data.get("s2", self.s2))
            except Exception:
                pass

    def save_config(self):
        data = {
            "port": self.selected_port.get(),
            "s1": self.s1,
            "s2": self.s2,
            "live": self.live_calibration.get(),
        }
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ------------------------- UI BUILD -------------------------

    def build_layout(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkScrollableFrame(
            self,
            width=260,
            fg_color=COLORS["sidebar"],
            corner_radius=0,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.main = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg"],
            corner_radius=0,
        )
        self.main.grid(row=0, column=1, sticky="nsew", padx=16, pady=14)

        self.build_sidebar()
        self.build_main()

    def build_sidebar(self):
        ctk.CTkLabel(
            self.sidebar,
            text="SPIROB\nMISSION CONTROL",
            font=("Arial", 24, "bold"),
            justify="left",
        ).pack(anchor="w", padx=18, pady=(18, 4))

        ctk.CTkLabel(
            self.sidebar,
            text="Bluetooth kontrolni interfejs\nHC-06 • STM32F103C8T6 • Servo drive",
            text_color=COLORS["muted"],
            font=("Arial", 11),
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 12))

        connection = self.sidebar_card("KONEKCIJA")

        self.port_menu = ctk.CTkOptionMenu(
            connection,
            values=["-"],
            variable=self.selected_port,
            height=34,
            fg_color="#1f2b3d",
            button_color="#1d4ed8",
            button_hover_color="#2563eb",
        )
        self.port_menu.pack(fill="x", pady=(8, 8))

        ctk.CTkButton(connection, text="OSVJEŽI PORTOVE", command=self.refresh_ports, height=36).pack(fill="x", pady=4)
        ctk.CTkButton(connection, text="POVEŽI SISTEM", command=self.connect, height=40, fg_color=COLORS["blue"]).pack(fill="x", pady=4)
        ctk.CTkButton(connection, text="PREKINI VEZU", command=self.disconnect, height=36, fg_color=COLORS["slate"]).pack(fill="x", pady=4)

        hardware = self.sidebar_card("HARDVER MAPA")
        self.hardware_canvas = ctk.CTkCanvas(hardware, width=224, height=172, bg=COLORS["card"], highlightthickness=0)
        self.hardware_canvas.pack(pady=(4, 8))
        self.draw_hardware_map(False)

        hardware_rows = [
            ("Baud", "9600"),
            ("Bluetooth", "HC-06"),
            ("MCU", "STM32F103C8T6"),
            ("BT TX/RX", "PA9 / PA10"),
            ("Servo 1", "PA0"),
            ("Servo 2", "PA1"),
            ("Power", "vanjski 5V/6V"),
        ]
        for name, value in hardware_rows:
            row = ctk.CTkFrame(hardware, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(
                row,
                text=f"{name}:",
                width=82,
                anchor="w",
                font=("Consolas", 10),
                text_color=COLORS["soft"] if "soft" in COLORS else "#cbd5e1",
            ).pack(side="left")
            ctk.CTkLabel(row, text=value, anchor="w", font=("Consolas", 10, "bold")).pack(side="left")

        indicators = self.sidebar_card("INDIKATORI")
        gauges = ctk.CTkFrame(indicators, fg_color="transparent")
        gauges.pack(fill="x", pady=(8, 2))
        gauges.grid_columnconfigure((0, 1), weight=1)

        self.grip_gauge = RingGauge(gauges, "GRIP", COLORS["green"], size=82)
        self.grip_gauge.grid(row=0, column=0, padx=(0, 6), sticky="nsew")

        self.link_gauge = RingGauge(gauges, "LINK", "#60a5fa", size=82)
        self.link_gauge.grid(row=0, column=1, padx=(6, 0), sticky="nsew")

        ctk.CTkLabel(
            indicators,
            text="Digital Twin prikazuje očekivano stanje.\nZa realnu silu/struju potreban je dodatni senzor.",
            text_color=COLORS["muted"],
            font=("Arial", 10),
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

    def build_main(self):
        self.status_card = ctk.CTkFrame(self.main, fg_color=COLORS["card"], corner_radius=18, height=54)
        self.status_card.pack(fill="x", pady=(0, 10))
        self.status_card.pack_propagate(False)
        self.status_card.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(self.status_card, text="● OFFLINE", text_color=COLORS["red_soft"], font=("Arial", 18, "bold"))
        self.status_label.grid(row=0, column=0, padx=20, pady=14, sticky="w")

        self.latency_label = ctk.CTkLabel(self.status_card, text="Latency: - ms    COM: -", font=("Consolas", 11), text_color=COLORS["text"])
        self.latency_label.grid(row=0, column=1, padx=20, pady=14, sticky="e")

        metrics = ctk.CTkFrame(self.main, fg_color="transparent")
        metrics.pack(fill="x", pady=(0, 10))
        metrics.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.metric_cmd = self.metric_box(metrics, 0, "ZADNJA KOMANDA", self.last_command, COLORS["blue"])
        self.metric_mode = self.metric_box(metrics, 1, "REŽIM RADA", "Ručno", COLORS["text"])
        self.metric_s1 = self.metric_box(metrics, 2, "SERVO 1", f"{self.s1}°", "#facc15")
        self.metric_s2 = self.metric_box(metrics, 3, "SERVO 2", f"{self.s2}°", "#facc15")

        self.build_control_panel()
        self.build_work_area()
        self.build_log_panel()

    def sidebar_card(self, title):
        frame = ctk.CTkFrame(self.sidebar, fg_color=COLORS["card"], corner_radius=18)
        frame.pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(
            frame,
            text=title,
            text_color="#60a5fa",
            font=("Arial", 12, "bold"),
        ).pack(anchor="w", padx=14, pady=(14, 4))

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=(4, 14))
        return inner

    def metric_box(self, parent, column, label, value, color):
        frame = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=16, height=74)
        frame.grid(row=0, column=column, sticky="ew", padx=5)
        frame.pack_propagate(False)

        ctk.CTkLabel(
            frame,
            text=label,
            text_color="#93c5fd",
            font=("Arial", 10, "bold"),
        ).pack(anchor="w", padx=14, pady=(10, 1))

        value_label = ctk.CTkLabel(
            frame,
            text=value,
            text_color=color,
            font=("Arial", 18, "bold"),
        )
        value_label.pack(anchor="w", padx=14, pady=(0, 10))
        return value_label

    def build_control_panel(self):
        panel = ctk.CTkFrame(self.main, fg_color=COLORS["card"], corner_radius=18)
        panel.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(panel, text="Upravljanje", font=("Arial", 18, "bold")).pack(anchor="w", padx=18, pady=(14, 8))

        grid = ctk.CTkFrame(panel, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(0, 14))
        grid.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.command_button(grid, "UHVATI", "g", COLORS["blue"], 0, 0, "Start sekvence")
        self.command_button(grid, "E-STOP / PUSTI", "f", COLORS["red"], 0, 1, "Sigurno zaustavljanje")
        self.command_button(grid, "HOME", "h", COLORS["slate"], 0, 2, "Početni položaj")
        self.command_button(grid, "OTVORI", "o", COLORS["slate"], 0, 3, "Otpuštanje")

        self.command_button(grid, "ZATEGNI", "c", COLORS["slate"], 1, 0, "Finalni grip")
        self.command_button(grid, "TEST S1", "1", COLORS["amber"], 1, 1, "Dijagnostika")
        self.command_button(grid, "TEST S2", "2", COLORS["amber"], 1, 2, "Dijagnostika")
        self.command_button(grid, "PING", "?", COLORS["amber"], 1, 3, "Provjera veze")

    def build_work_area(self):
        work = ctk.CTkFrame(self.main, fg_color="transparent")
        work.pack(fill="both", expand=False, pady=(0, 10))
        work.grid_columnconfigure(0, weight=1)
        work.grid_columnconfigure(1, weight=1)

        twin = ctk.CTkFrame(work, fg_color=COLORS["card"], corner_radius=18)
        twin.grid(row=0, column=0, sticky="new", padx=(0, 6))

        ctk.CTkLabel(twin, text="Digital Twin / Wireframe", font=("Arial", 18, "bold")).pack(anchor="w", padx=18, pady=(14, 8))
        self.twin_canvas = ctk.CTkCanvas(twin, height=245, bg=COLORS["card_dark"], highlightthickness=0)
        self.twin_canvas.pack(fill="x", padx=14, pady=(0, 14))

        self.calibration = ctk.CTkFrame(work, fg_color=COLORS["card"], corner_radius=18)
        self.calibration.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.build_calibration_panel(self.calibration)

    def build_calibration_panel(self, parent):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(14, 4))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="Kalibracija pokreta", font=("Arial", 18, "bold")).grid(row=0, column=0, sticky="w")

        self.live_switch = ctk.CTkSwitch(
            header,
            text="LIVE",
            variable=self.live_calibration,
            command=self.on_live_toggle,
            progress_color=COLORS["green"],
            font=("Arial", 11, "bold"),
        )
        self.live_switch.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(
            parent,
            text="Slider prvo mijenja preview. Klikni PRIMIJENI OBA za sigurno slanje. Uključi LIVE za direktno pomjeranje.",
            text_color=COLORS["muted"],
            font=("Arial", 10),
            wraplength=650,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 8))

        self.s1_label, self.s1_slider = self.servo_slider(parent, "Servo 1 ugao", "PA0", self.s1, lambda v: self.slider_changed("A", int(float(v))))
        self.s2_label, self.s2_slider = self.servo_slider(parent, "Servo 2 ugao", "PA1", self.s2, lambda v: self.slider_changed("B", int(float(v))))

        buttons = ctk.CTkFrame(parent, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(8, 8))
        buttons.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(buttons, text="PRIMIJENI OBA", command=self.apply_both, height=38, fg_color=COLORS["blue"], font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(buttons, text="HOME SET", command=self.home_preview, height=38, fg_color=COLORS["slate"], font=("Arial", 12, "bold")).grid(row=0, column=1, sticky="ew", padx=6)
        ctk.CTkButton(buttons, text="GRIP SET", command=self.grip_preview, height=38, fg_color=COLORS["slate"], font=("Arial", 12, "bold")).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        self.live_hint = ctk.CTkLabel(
            parent,
            text="LIVE isključen: podešavanje je sigurno i ne šalje komande dok ne klikneš PRIMIJENI OBA.",
            text_color=COLORS["muted"],
            font=("Consolas", 10),
        )
        self.live_hint.pack(anchor="w", padx=18, pady=(0, 14))

    def servo_slider(self, parent, title, pin, value, command):
        box = ctk.CTkFrame(parent, fg_color=COLORS["card_dark"], corner_radius=16)
        box.pack(fill="x", padx=18, pady=6)

        top = ctk.CTkFrame(box, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 2))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text=title, font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(top, text=pin, text_color=COLORS["muted"], font=("Consolas", 10, "bold")).grid(row=0, column=1, sticky="w", padx=10)

        value_label = ctk.CTkLabel(
            top,
            text=f"{value}°",
            width=58,
            height=26,
            fg_color="#1f2937",
            text_color="#facc15",
            corner_radius=13,
            font=("Consolas", 13, "bold"),
        )
        value_label.grid(row=0, column=2, sticky="e")

        slider = ctk.CTkSlider(
            box,
            from_=0,
            to=180,
            command=command,
            progress_color="#64748b",
            button_color="#1f77b4",
            button_hover_color="#38bdf8",
        )
        slider.set(value)
        slider.pack(fill="x", padx=14, pady=(5, 6))

        marks = ctk.CTkFrame(box, fg_color="transparent")
        marks.pack(fill="x", padx=14, pady=(0, 8))
        marks.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(marks, text="0°", text_color=COLORS["muted"], font=("Consolas", 8)).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(marks, text="90°", text_color=COLORS["muted"], font=("Consolas", 8)).grid(row=0, column=1)
        ctk.CTkLabel(marks, text="180°", text_color=COLORS["muted"], font=("Consolas", 8)).grid(row=0, column=2, sticky="e")

        return value_label, slider

    def build_log_panel(self):
        panel = ctk.CTkFrame(self.main, fg_color=COLORS["card"], corner_radius=18)
        panel.pack(fill="x", pady=(0, 10))

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(12, 6))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="Napredni komunikacijski log", font=("Arial", 18, "bold")).grid(row=0, column=0, sticky="w")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e")

        ctk.CTkButton(actions, text="CLEAR", command=self.clear_log, width=70, height=30, fg_color=COLORS["slate"]).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="EXPORT", command=self.export_log, width=80, height=30, fg_color=COLORS["slate"]).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="PLAY MACRO", command=self.play_macro, width=100, height=30).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="REC MACRO", command=self.toggle_record, width=95, height=30).pack(side="left", padx=4)

        self.log_text = ctk.CTkTextbox(
            panel,
            height=125,
            fg_color=COLORS["console"],
            border_width=1,
            border_color=COLORS["border"],
            corner_radius=12,
            font=("Consolas", 11),
            wrap="none",
        )
        self.log_text.pack(fill="x", padx=18, pady=(0, 14))

    def command_button(self, parent, text, cmd, color, row, col, subtitle):
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=row, column=col, sticky="ew", padx=8, pady=6)

        ctk.CTkButton(
            cell,
            text=text,
            command=lambda: self.command_action(cmd),
            fg_color=color,
            height=38,
            font=("Arial", 12, "bold"),
        ).pack(fill="x")

        ctk.CTkLabel(
            cell,
            text=subtitle,
            text_color=COLORS["muted"],
            font=("Arial", 9),
        ).pack(pady=(3, 0))

    # ------------------------- DRAWING -------------------------

    def draw_hardware_map(self, active):
        c = self.hardware_canvas
        c.delete("all")

        # Canvas je namjerno širi i sve oznake su povučene unutra
        # da se ne sijeku na lijevoj/desnoj ivici sidebar-a.
        w = int(c["width"])
        box_x1, box_y1 = 78, 28
        box_x2, box_y2 = 154, 132
        cx = (box_x1 + box_x2) // 2

        c.create_rectangle(box_x1, box_y1, box_x2, box_y2, outline="#4b5563", width=2)
        c.create_text(cx, 68, text="STM32\nF103C8T6", fill="white", font=("Consolas", 10, "bold"))

        left_dot_x = 56
        left_text_x = 8
        right_dot_x = 172
        right_text_x = 188

        pin_color = "#60a5fa" if active else "#64748b"

        left_pins = [
            (58, "PA10 RX"),
            (84, "PA9 TX"),
        ]
        right_pins = [
            (58, "PA0 S1"),
            (84, "PA1 S2"),
        ]

        for y, label in left_pins:
            c.create_text(left_text_x, y, text=label, fill="white", font=("Consolas", 8), anchor="w")
            c.create_oval(left_dot_x - 6, y - 6, left_dot_x + 6, y + 6, fill=pin_color, outline="")

        for y, label in right_pins:
            c.create_oval(right_dot_x - 6, y - 6, right_dot_x + 6, y + 6, fill=pin_color, outline="")
            c.create_text(right_text_x, y, text=label, fill="white", font=("Consolas", 8), anchor="w")

        c.create_oval(cx - 6, 116, cx + 6, 128, fill=COLORS["green"], outline="")
        c.create_text(cx, 154, text="GND", fill="white", font=("Consolas", 8))

    def draw_digital_twin(self):
        if not hasattr(self, "twin_canvas"):
            return

        c = self.twin_canvas
        c.delete("all")

        width = max(c.winfo_width(), 560)
        height = max(c.winfo_height(), 235)

        label_y = 26
        top_safe = 54
        bottom_safe = 18

        cx = width / 2
        cy = top_safe + (height - top_safe - bottom_safe) / 2 + 8

        ratio = max(0.0, min(1.0, self.grip / 100.0))

        c.create_text(
            24,
            label_y,
            text=f"Grip intensity: {self.grip}%",
            fill="white",
            anchor="w",
            font=("Consolas", 13, "bold"),
        )

        # Automatsko skaliranje: krakovi nikad ne izlaze iz canvas-a.
        available_top = cy - top_safe
        available_bottom = height - cy - bottom_safe
        available_side = width * 0.30
        max_reach = max(70, min(105, available_top, available_bottom, available_side))

        core_r = max(36, min(48, max_reach * 0.38))
        joint_r = core_r + 10
        remaining = max_reach - joint_r
        seg1 = max(26, remaining * 0.62)
        seg2 = max(18, remaining * 0.38)

        c.create_oval(cx - core_r, cy - core_r, cx + core_r, cy + core_r, outline="#334155", width=2)
        c.create_text(cx, cy, text="GRAPPLER", fill="white", font=("Arial", 11, "bold"))

        for i in range(6):
            a = math.radians(i * 60 - 90)
            curl = math.radians(16 + 50 * ratio)

            x0 = cx + math.cos(a) * joint_r
            y0 = cy + math.sin(a) * joint_r

            x1 = x0 + math.cos(a + curl) * seg1
            y1 = y0 + math.sin(a + curl) * seg1

            x2 = x1 + math.cos(a + curl * 1.35) * seg2
            y2 = y1 + math.sin(a + curl * 1.35) * seg2

            c.create_line(x0, y0, x1, y1, fill="#60a5fa", width=4)
            c.create_line(x1, y1, x2, y2, fill="#60a5fa", width=3)
            c.create_oval(x0 - 5, y0 - 5, x0 + 5, y0 + 5, fill=COLORS["card_dark"], outline="#93c5fd")
            c.create_oval(x2 - 3, y2 - 3, x2 + 3, y2 + 3, fill="#60a5fa", outline="")

    # ------------------------- SERIAL -------------------------

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
            self.disconnect(silent=True)
            self.ser = serial.Serial(port, BAUD, timeout=0.08)
            self.connected = True
            self.reader_running = True
            self.reader_thread = threading.Thread(target=self.reader_loop, daemon=True)
            self.reader_thread.start()
            self.save_config()
            self.log("OK", f"Povezano na {port} pri {BAUD} baud.")
            self.after(250, lambda: self.send_command("?"))
        except Exception as exc:
            self.connected = False
            self.ser = None
            self.log("ERROR", f"Ne mogu otvoriti {port}: {exc}")

    def disconnect(self, silent=False):
        self.reader_running = False
        self.connected = False

        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass

        self.ser = None

        if not silent:
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
            self.metric_cmd.configure(text=cmd)
            self.log("TX", frame)

            if self.recording:
                self.macro.append(cmd)

            return True
        except Exception as exc:
            self.log("ERROR", f"Slanje nije uspjelo: {exc}")
            return False

    def reader_loop(self):
        buffer = ""

        while self.reader_running:
            try:
                if not self.ser:
                    break

                data = self.ser.read(128)
                if data:
                    text = data.decode("utf-8", errors="ignore")

                    for ch in text:
                        if ch == "\n":
                            line = buffer.strip()
                            buffer = ""
                            if line:
                                self.after(0, lambda x=line: self.handle_rx(x))
                        elif ch != "\r":
                            buffer += ch
                else:
                    time.sleep(0.02)
            except Exception as exc:
                self.after(0, lambda: self.log("ERROR", f"Reader error: {exc}"))
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
            data = {}

            for item in payload.split(";"):
                if "=" in item:
                    key, value = item.split("=", 1)
                    data[key.strip()] = value.strip()

            self.s1 = int(data.get("S1", self.s1))
            self.s2 = int(data.get("S2", self.s2))
            self.grip = int(data.get("GRIP", self.grip))

            self.s1_slider.set(self.s1)
            self.s2_slider.set(self.s2)
            self.s1_label.configure(text=f"{self.s1}°")
            self.s2_label.configure(text=f"{self.s2}°")
            self.update_values()
        except Exception as exc:
            self.log("WARN", f"Ne mogu parsirati STATE: {exc}")

    # ------------------------- ACTIONS -------------------------

    def command_action(self, cmd):
        ok = self.send_command(cmd)

        if not ok:
            return

        if cmd in ("g", "c"):
            self.s1 = SERVO1_GRIP
            self.s2 = SERVO2_GRIP
            self.update_sliders_from_values()
        elif cmd in ("f", "h", "o"):
            self.s1 = SERVO1_HOME
            self.s2 = SERVO2_HOME
            self.update_sliders_from_values()

    def slider_changed(self, servo, value):
        if servo == "A":
            self.s1 = value
            self.s1_label.configure(text=f"{self.s1}°")
            self.schedule_live("A", self.s1)
        else:
            self.s2 = value
            self.s2_label.configure(text=f"{self.s2}°")
            self.schedule_live("B", self.s2)

        self.grip = self.estimate_grip()
        self.update_values()

    def schedule_live(self, servo, value):
        if not self.live_calibration.get():
            return

        job_attr = "live_job_s1" if servo == "A" else "live_job_s2"
        old_job = getattr(self, job_attr)

        if old_job:
            try:
                self.after_cancel(old_job)
            except Exception:
                pass

        new_job = self.after(140, lambda: self.send_command(f"{servo}{value:03d}"))
        setattr(self, job_attr, new_job)

    def on_live_toggle(self):
        if self.live_calibration.get():
            self.metric_mode.configure(text="Live kalibracija")
            self.live_hint.configure(
                text="LIVE uključen: servo se pomjera dok pomjeraš slider, sa debounce zaštitom.",
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

    def apply_both(self):
        if self.send_command(f"A{self.s1:03d}"):
            self.after(170, lambda: self.send_command(f"B{self.s2:03d}"))
            self.save_config()

    def home_preview(self):
        self.s1 = SERVO1_HOME
        self.s2 = SERVO2_HOME
        self.update_sliders_from_values()
        self.log("INFO", "Preview postavljen na HOME. Klikni PRIMIJENI OBA za slanje.")

    def grip_preview(self):
        self.s1 = SERVO1_GRIP
        self.s2 = SERVO2_GRIP
        self.update_sliders_from_values()
        self.log("INFO", "Preview postavljen na GRIP. Klikni PRIMIJENI OBA za slanje.")

    def update_sliders_from_values(self):
        self.s1_slider.set(self.s1)
        self.s2_slider.set(self.s2)
        self.s1_label.configure(text=f"{self.s1}°")
        self.s2_label.configure(text=f"{self.s2}°")
        self.grip = self.estimate_grip()
        self.update_values()

    def estimate_grip(self):
        p1 = (SERVO1_HOME - self.s1) / max(1, SERVO1_HOME - SERVO1_GRIP)
        p2 = (self.s2 - SERVO2_HOME) / max(1, SERVO2_GRIP - SERVO2_HOME)
        p1 = max(0, min(1, p1))
        p2 = max(0, min(1, p2))
        return int((p1 + p2) * 50)

    def update_values(self):
        self.metric_s1.configure(text=f"{self.s1}°")
        self.metric_s2.configure(text=f"{self.s2}°")
        self.grip_gauge.set_value(self.grip)
        self.draw_digital_twin()

    # ------------------------- LOG AND MACRO -------------------------

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
                time.sleep(0.65)

        threading.Thread(target=worker, daemon=True).start()

    def export_log(self):
        data = {
            "exported_at": datetime.now().isoformat(),
            "logs": self.logs,
            "macro": self.macro,
        }

        EXPORT_LOG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.log("OK", f"Log exportovan u {EXPORT_LOG_FILE}")

    def clear_log(self):
        self.logs = []
        self.log_text.delete("1.0", "end")

    def log(self, level, message):
        line = f"[{timestamp()}] [{level}] {message}"
        self.logs.append(line)

        if len(self.logs) > 400:
            self.logs = self.logs[-400:]

        if hasattr(self, "log_text"):
            self.log_text.insert("end", line + "\n")
            self.log_text.see("end")

    # ------------------------- REFRESH -------------------------

    def refresh_ui(self):
        if self.connected:
            self.status_label.configure(text="● ONLINE", text_color=COLORS["green"])
            self.link_gauge.set_value(100)
            self.draw_hardware_map(True)
        else:
            self.status_label.configure(text="● OFFLINE", text_color=COLORS["red_soft"])
            self.link_gauge.set_value(0)
            self.draw_hardware_map(False)

        latency = "-"
        if self.connected and self.last_ack_time:
            latency = str(int((time.time() - self.last_ack_time) * 1000))

        self.latency_label.configure(text=f"Latency: {latency} ms    COM: {self.selected_port.get()}")
        self.after(1000, self.refresh_ui)


if __name__ == "__main__":
    app = SpiRobDesktopApp()
    app.mainloop()
