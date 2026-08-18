import customtkinter as ctk
import serial
from serial.tools import list_ports
from datetime import datetime
from tkinter import messagebox

BAUD = 9600
ser = None

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def available_ports():
    return [p.device for p in list_ports.comports()]


class GrapplerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SpiRob Grappler Control System")
        self.geometry("1050x650")
        self.minsize(950, 580)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.create_sidebar()
        self.create_main_panel()
        self.refresh_ports()
        self.after(300, self.auto_read)

    def create_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(9, weight=1)

        self.logo = ctk.CTkLabel(
            self.sidebar,
            text="SPIROB\nGRAPPLER",
            font=ctk.CTkFont(size=30, weight="bold"),
            justify="left"
        )
        self.logo.grid(row=0, column=0, padx=28, pady=(28, 8), sticky="w")

        self.subtitle = ctk.CTkLabel(
            self.sidebar,
            text="Bluetooth Control Interface\nHC-06 • Arduino • Servo Drive",
            font=ctk.CTkFont(size=13),
            text_color="#9ca3af",
            justify="left"
        )
        self.subtitle.grid(row=1, column=0, padx=28, pady=(0, 28), sticky="w")

        self.connection_title = ctk.CTkLabel(
            self.sidebar,
            text="KONEKCIJA",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#60a5fa"
        )
        self.connection_title.grid(row=2, column=0, padx=28, pady=(5, 8), sticky="w")

        self.port_var = ctk.StringVar(value="")
        self.port_menu = ctk.CTkOptionMenu(
            self.sidebar,
            variable=self.port_var,
            values=["Nema portova"],
            height=38
        )
        self.port_menu.grid(row=3, column=0, padx=28, pady=6, sticky="ew")

        self.refresh_btn = ctk.CTkButton(
            self.sidebar,
            text="Osvježi portove",
            height=38,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.refresh_ports
        )
        self.refresh_btn.grid(row=4, column=0, padx=28, pady=6, sticky="ew")

        self.connect_btn = ctk.CTkButton(
            self.sidebar,
            text="Poveži sistem",
            height=42,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self.connect
        )
        self.connect_btn.grid(row=5, column=0, padx=28, pady=(18, 6), sticky="ew")

        self.disconnect_btn = ctk.CTkButton(
            self.sidebar,
            text="Prekini vezu",
            height=42,
            fg_color="#991b1b",
            hover_color="#7f1d1d",
            command=self.disconnect,
            state="disabled"
        )
        self.disconnect_btn.grid(row=6, column=0, padx=28, pady=6, sticky="ew")

        self.status_card = ctk.CTkFrame(self.sidebar, corner_radius=16, fg_color="#111827")
        self.status_card.grid(row=7, column=0, padx=28, pady=(24, 10), sticky="ew")

        self.status_label = ctk.CTkLabel(
            self.status_card,
            text="STATUS SISTEMA",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#9ca3af"
        )
        self.status_label.pack(anchor="w", padx=16, pady=(14, 2))

        self.status_value = ctk.CTkLabel(
            self.status_card,
            text="OFFLINE",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#ef4444"
        )
        self.status_value.pack(anchor="w", padx=16, pady=(0, 14))

        self.info_card = ctk.CTkFrame(self.sidebar, corner_radius=16, fg_color="#111827")
        self.info_card.grid(row=8, column=0, padx=28, pady=10, sticky="ew")

        info = (
            "Baud rate: 9600\n"
            "Bluetooth: HC-06\n"
            "BT RX/TX: D10/D11\n"
            "Servo 1: D6\n"
            "Servo 2: D5\n"
            "Napajanje: vanjski 5V"
        )

        self.info_label = ctk.CTkLabel(
            self.info_card,
            text=info,
            font=ctk.CTkFont(size=13),
            text_color="#d1d5db",
            justify="left"
        )
        self.info_label.pack(anchor="w", padx=16, pady=16)

    def create_main_panel(self):
        self.main = ctk.CTkFrame(self, corner_radius=0, fg_color="#0b1120")
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(3, weight=1)

        self.header = ctk.CTkFrame(self.main, fg_color="transparent")
        self.header.grid(row=0, column=0, padx=32, pady=(28, 10), sticky="ew")
        self.header.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            self.header,
            text="Kontrolni panel za robotski grappler",
            font=ctk.CTkFont(size=28, weight="bold")
        )
        self.title_label.grid(row=0, column=0, sticky="w")

        self.description = ctk.CTkLabel(
            self.header,
            text="Profesionalni interfejs za upravljanje hvatanjem, otpuštanjem i testiranjem servo aktuatora.",
            font=ctk.CTkFont(size=14),
            text_color="#9ca3af"
        )
        self.description.grid(row=1, column=0, pady=(5, 0), sticky="w")

        self.metrics = ctk.CTkFrame(self.main, fg_color="transparent")
        self.metrics.grid(row=1, column=0, padx=32, pady=14, sticky="ew")
        self.metrics.grid_columnconfigure((0, 1, 2), weight=1)

        self.metric_command = self.metric_card("Zadnja komanda", "Nema", "#60a5fa")
        self.metric_command.grid(row=0, column=0, padx=(0, 10), sticky="ew")

        self.metric_connection = self.metric_card("Konekcija", "Nije povezan", "#ef4444")
        self.metric_connection.grid(row=0, column=1, padx=10, sticky="ew")

        self.metric_mode = self.metric_card("Režim rada", "Ručno", "#22c55e")
        self.metric_mode.grid(row=0, column=2, padx=(10, 0), sticky="ew")

        self.controls = ctk.CTkFrame(self.main, corner_radius=22, fg_color="#111827")
        self.controls.grid(row=2, column=0, padx=32, pady=(6, 18), sticky="ew")
        self.controls.grid_columnconfigure((0, 1, 2), weight=1)

        self.control_title = ctk.CTkLabel(
            self.controls,
            text="Upravljanje sistemom",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.control_title.grid(row=0, column=0, columnspan=3, padx=24, pady=(22, 12), sticky="w")

        self.buttons = []

        self.btn_grab = self.big_button(
            "UHVATI",
            "Pokreni sekvencu hvatanja",
            "#2563eb",
            "#1d4ed8",
            lambda: self.send("g", "Uhvati")
        )
        self.btn_grab.grid(row=1, column=0, padx=18, pady=12, sticky="ew")
        self.buttons.append(self.btn_grab)

        self.btn_stop = self.big_button(
            "STOP / PUSTI",
            "Prekini rad i otpusti",
            "#dc2626",
            "#b91c1c",
            lambda: self.send("f", "Stop / Pusti")
        )
        self.btn_stop.grid(row=1, column=1, padx=18, pady=12, sticky="ew")
        self.buttons.append(self.btn_stop)

        self.btn_home = self.big_button(
            "HOME",
            "Vrati servoe na početak",
            "#374151",
            "#4b5563",
            lambda: self.send("h", "Home")
        )
        self.btn_home.grid(row=1, column=2, padx=18, pady=12, sticky="ew")
        self.buttons.append(self.btn_home)

        self.btn_open = self.small_button("OTVORI", lambda: self.send("o", "Otvori"))
        self.btn_open.grid(row=2, column=0, padx=18, pady=(8, 22), sticky="ew")
        self.buttons.append(self.btn_open)

        self.btn_close = self.small_button("ZATEGNI", lambda: self.send("c", "Zategni"))
        self.btn_close.grid(row=2, column=1, padx=18, pady=(8, 22), sticky="ew")
        self.buttons.append(self.btn_close)

        self.btn_test = self.small_button("TEST SERVO 1 / 2", self.open_test_window)
        self.btn_test.grid(row=2, column=2, padx=18, pady=(8, 22), sticky="ew")
        self.buttons.append(self.btn_test)

        self.log_panel = ctk.CTkFrame(self.main, corner_radius=22, fg_color="#111827")
        self.log_panel.grid(row=3, column=0, padx=32, pady=(0, 28), sticky="nsew")
        self.log_panel.grid_columnconfigure(0, weight=1)
        self.log_panel.grid_rowconfigure(1, weight=1)

        self.log_header = ctk.CTkFrame(self.log_panel, fg_color="transparent")
        self.log_header.grid(row=0, column=0, padx=24, pady=(20, 10), sticky="ew")
        self.log_header.grid_columnconfigure(0, weight=1)

        self.log_title = ctk.CTkLabel(
            self.log_header,
            text="Komunikacijski log",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.log_title.grid(row=0, column=0, sticky="w")

        self.clear_log_btn = ctk.CTkButton(
            self.log_header,
            text="Očisti log",
            width=110,
            height=32,
            fg_color="#1f2937",
            hover_color="#374151",
            command=self.clear_log
        )
        self.clear_log_btn.grid(row=0, column=1, sticky="e")

        self.log_box = ctk.CTkTextbox(
            self.log_panel,
            corner_radius=14,
            fg_color="#020617",
            text_color="#e5e7eb",
            font=ctk.CTkFont(family="Consolas", size=13)
        )
        self.log_box.grid(row=1, column=0, padx=24, pady=(0, 24), sticky="nsew")

        self.set_controls(False)

    def metric_card(self, label, value, color):
        frame = ctk.CTkFrame(self.metrics, corner_radius=18, fg_color="#111827")

        title = ctk.CTkLabel(
            frame,
            text=label,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#9ca3af"
        )
        title.pack(anchor="w", padx=18, pady=(15, 2))

        val = ctk.CTkLabel(
            frame,
            text=value,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=color
        )
        val.pack(anchor="w", padx=18, pady=(0, 16))

        frame.value_label = val
        return frame

    def big_button(self, title, subtitle, color, hover, command):
        frame = ctk.CTkFrame(self.controls, corner_radius=18, fg_color="#0f172a")

        btn = ctk.CTkButton(
            frame,
            text=title,
            height=50,
            corner_radius=14,
            fg_color=color,
            hover_color=hover,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=command
        )
        btn.pack(fill="x", padx=14, pady=(14, 5))

        lbl = ctk.CTkLabel(
            frame,
            text=subtitle,
            font=ctk.CTkFont(size=12),
            text_color="#9ca3af"
        )
        lbl.pack(pady=(0, 12))

        frame.button = btn
        return frame

    def small_button(self, text, command):
        return ctk.CTkButton(
            self.controls,
            text=text,
            height=44,
            corner_radius=14,
            fg_color="#1f2937",
            hover_color="#374151",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=command
        )

    def open_test_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Test servo motora")
        win.geometry("360x260")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()
        win.focus()

        label = ctk.CTkLabel(
            win,
            text="Test aktuatora",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        label.pack(pady=(28, 8))

        desc = ctk.CTkLabel(
            win,
            text="Pokreni pojedinačni test servo motora.",
            text_color="#9ca3af"
        )
        desc.pack(pady=(0, 18))

        ctk.CTkButton(
            win,
            text="Test servo 1",
            height=44,
            command=lambda: self.send("1", "Test servo 1")
        ).pack(fill="x", padx=38, pady=8)

        ctk.CTkButton(
            win,
            text="Test servo 2",
            height=44,
            command=lambda: self.send("2", "Test servo 2")
        ).pack(fill="x", padx=38, pady=8)

        ctk.CTkButton(
            win,
            text="Zatvori",
            height=38,
            fg_color="#374151",
            hover_color="#4b5563",
            command=win.destroy
        ).pack(fill="x", padx=38, pady=(18, 8))

    def log(self, msg, level="INFO"):
        now = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{now}] [{level}] {msg}\n")
        self.log_box.see("end")

    def clear_log(self):
        self.log_box.delete("1.0", "end")
        self.log("Log očišćen.", "INFO")

    def set_controls(self, enabled):
        state = "normal" if enabled else "disabled"

        for b in self.buttons:
            if hasattr(b, "button"):
                b.button.configure(state=state)
            else:
                b.configure(state=state)

    def refresh_ports(self):
        ports = available_ports()

        if not ports:
            self.port_menu.configure(values=["Nema portova"])
            self.port_var.set("Nema portova")
            return

        self.port_menu.configure(values=ports)

        if "COM4" in ports:
            self.port_var.set("COM4")
        else:
            self.port_var.set(ports[0])

        if hasattr(self, "log_box"):
            self.log("COM portovi osvježeni.", "INFO")

    def connect(self):
        global ser

        port = self.port_var.get()

        if not port or port == "Nema portova":
            messagebox.showwarning("Greška", "Nije izabran COM port.")
            return

        try:
            ser = serial.Serial(port, BAUD, timeout=0.2)

            self.status_value.configure(text="ONLINE", text_color="#22c55e")
            self.metric_connection.value_label.configure(text=port, text_color="#22c55e")
            self.metric_mode.value_label.configure(text="Spreman", text_color="#22c55e")
            self.connect_btn.configure(state="disabled")
            self.disconnect_btn.configure(state="normal")
            self.set_controls(True)

            self.log(f"Sistem povezan na {port} pri {BAUD} baud.", "OK")

        except serial.SerialException as e:
            self.log(f"Greška pri povezivanju: {e}", "ERROR")
            messagebox.showerror(
                "Greška",
                "Ne mogu otvoriti COM port.\n\n"
                "Zatvori Arduino Serial Monitor, PuTTY ili drugi program koji koristi isti port."
            )

    def disconnect(self):
        global ser

        if ser is not None:
            try:
                if ser.is_open:
                    ser.close()
            except Exception:
                pass

        ser = None

        self.status_value.configure(text="OFFLINE", text_color="#ef4444")
        self.metric_connection.value_label.configure(text="Nije povezan", text_color="#ef4444")
        self.metric_mode.value_label.configure(text="Ručno", text_color="#22c55e")
        self.connect_btn.configure(state="normal")
        self.disconnect_btn.configure(state="disabled")
        self.set_controls(False)

        if hasattr(self, "log_box"):
            self.log("Konekcija je prekinuta.", "INFO")

    def send(self, cmd, description):
        global ser

        if ser is None or not ser.is_open:
            self.log("Komanda nije poslana jer sistem nije povezan.", "WARN")
            return

        try:
            ser.write(cmd.encode())
            ser.flush()

            self.metric_command.value_label.configure(text=description, text_color="#60a5fa")
            self.metric_mode.value_label.configure(text="Aktivno", text_color="#facc15")

            self.log(f"Poslana komanda: {description} ({cmd})", "TX")
            self.after(180, self.read_response)

        except serial.SerialException as e:
            self.log(f"Greška pri slanju: {e}", "ERROR")
            self.disconnect()

    def read_response(self):
        global ser

        if ser is None or not ser.is_open:
            return

        try:
            while ser.in_waiting:
                line = ser.readline().decode(errors="ignore").strip()

                if line:
                    self.log(f"Arduino: {line}", "RX")

                    upper_line = line.upper()

                    if "STOP" in upper_line or "HOME" in upper_line:
                        self.metric_mode.value_label.configure(text="Sigurno", text_color="#22c55e")
                    elif "DRZI" in upper_line or "OBJEKAT" in upper_line:
                        self.metric_mode.value_label.configure(text="Drži objekat", text_color="#22c55e")
                    elif "START" in upper_line or "FAZA" in upper_line:
                        self.metric_mode.value_label.configure(text="Aktivno", text_color="#facc15")

        except serial.SerialException as e:
            self.log(f"Greška pri čitanju: {e}", "ERROR")
            self.disconnect()

    def auto_read(self):
        self.read_response()
        self.after(300, self.auto_read)

    def on_close(self):
        self.disconnect()
        self.destroy()


if __name__ == "__main__":
    app = GrapplerApp()
    app.mainloop()