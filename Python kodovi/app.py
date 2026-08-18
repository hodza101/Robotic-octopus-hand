import tkinter as tk
from tkinter import ttk, messagebox
import serial
from serial.tools import list_ports
from datetime import datetime

BAUD = 9600
ser = None


# =========================
# SERIAL FUNKCIJE
# =========================

def get_ports():
    ports = list(list_ports.comports())
    return [p.device for p in ports]


def log(message, level="INFO"):
    time = datetime.now().strftime("%H:%M:%S")
    log_box.insert(tk.END, f"[{time}] [{level}] {message}\n")
    log_box.see(tk.END)


def set_status(text, color):
    status_text.config(text=text, foreground=color)


def refresh_ports():
    ports = get_ports()
    port_combo["values"] = ports

    if ports:
        if "COM4" in ports:
            port_var.set("COM4")
        else:
            port_var.set(ports[0])
        log("COM portovi osvježeni.")
    else:
        port_var.set("")
        log("Nema dostupnih COM portova.", "WARN")


def connect():
    global ser

    if ser is not None and ser.is_open:
        log("Već je povezano.", "WARN")
        return

    port = port_var.get().strip()

    if not port:
        messagebox.showwarning("Greška", "Nije izabran COM port.")
        return

    try:
        ser = serial.Serial(port, BAUD, timeout=0.2)
        set_status(f"Povezano: {port}", "#00cc66")
        connect_btn.config(state="disabled")
        disconnect_btn.config(state="normal")
        enable_controls(True)
        log(f"Povezano na {port} pri {BAUD} baud.")
    except serial.SerialException as e:
        set_status("Nije povezano", "#ff4444")
        log(f"Ne mogu otvoriti {port}: {e}", "ERROR")
        messagebox.showerror(
            "Greška pri povezivanju",
            f"Ne mogu otvoriti {port}.\n\n"
            "Provjeri da COM port nije otvoren u Arduino Serial Monitoru, PuTTY-ju ili drugom programu."
        )


def disconnect():
    global ser

    if ser is not None:
        try:
            if ser.is_open:
                ser.close()
                log("Konekcija zatvorena.")
        except Exception as e:
            log(f"Greška pri zatvaranju konekcije: {e}", "ERROR")

    ser = None
    set_status("Nije povezano", "#ff4444")
    connect_btn.config(state="normal")
    disconnect_btn.config(state="disabled")
    enable_controls(False)


def send(cmd, description):
    global ser

    if ser is None or not ser.is_open:
        set_status("Nije povezano", "#ff4444")
        log("Pokušaj slanja bez konekcije.", "WARN")
        return

    try:
        ser.write(cmd.encode())
        ser.flush()
        log(f"Poslana komanda: {description} ({cmd})")
        command_status.config(text=f"Zadnja komanda: {description}")
        root.after(150, read_response)
    except serial.SerialException as e:
        log(f"Greška pri slanju komande: {e}", "ERROR")
        disconnect()


def read_response():
    global ser

    if ser is None or not ser.is_open:
        return

    try:
        while ser.in_waiting:
            line = ser.readline().decode(errors="ignore").strip()
            if line:
                log(f"Arduino: {line}", "RX")
    except serial.SerialException as e:
        log(f"Greška pri čitanju odgovora: {e}", "ERROR")
        disconnect()


def auto_read():
    read_response()
    root.after(300, auto_read)


def enable_controls(enabled):
    state = "normal" if enabled else "disabled"

    for btn in control_buttons:
        btn.config(state=state)


def on_close():
    disconnect()
    root.destroy()


# =========================
# GUI
# =========================

root = tk.Tk()
root.title("Grappler Control Panel")
root.geometry("900x560")
root.minsize(820, 520)
root.configure(bg="#0f172a")
root.protocol("WM_DELETE_WINDOW", on_close)

style = ttk.Style()
style.theme_use("clam")

style.configure(
    "Main.TFrame",
    background="#0f172a"
)

style.configure(
    "Card.TFrame",
    background="#111827",
    relief="flat"
)

style.configure(
    "Title.TLabel",
    background="#0f172a",
    foreground="white",
    font=("Segoe UI", 22, "bold")
)

style.configure(
    "Subtitle.TLabel",
    background="#0f172a",
    foreground="#94a3b8",
    font=("Segoe UI", 10)
)

style.configure(
    "CardTitle.TLabel",
    background="#111827",
    foreground="white",
    font=("Segoe UI", 13, "bold")
)

style.configure(
    "Normal.TLabel",
    background="#111827",
    foreground="#cbd5e1",
    font=("Segoe UI", 10)
)

style.configure(
    "Status.TLabel",
    background="#111827",
    foreground="#ff4444",
    font=("Segoe UI", 11, "bold")
)

style.configure(
    "TCombobox",
    fieldbackground="#1f2937",
    background="#1f2937",
    foreground="white",
    arrowcolor="white"
)

style.configure(
    "Primary.TButton",
    font=("Segoe UI", 11, "bold"),
    padding=10,
    background="#2563eb",
    foreground="white"
)

style.map(
    "Primary.TButton",
    background=[("active", "#1d4ed8")]
)

style.configure(
    "Danger.TButton",
    font=("Segoe UI", 11, "bold"),
    padding=10,
    background="#dc2626",
    foreground="white"
)

style.map(
    "Danger.TButton",
    background=[("active", "#b91c1c")]
)

style.configure(
    "Secondary.TButton",
    font=("Segoe UI", 10),
    padding=8,
    background="#334155",
    foreground="white"
)

style.map(
    "Secondary.TButton",
    background=[("active", "#475569")]
)


main = ttk.Frame(root, style="Main.TFrame")
main.pack(fill="both", expand=True, padx=24, pady=20)

# HEADER
header = ttk.Frame(main, style="Main.TFrame")
header.pack(fill="x", pady=(0, 18))

title = ttk.Label(header, text="Grappler Control Panel", style="Title.TLabel")
title.pack(anchor="w")

subtitle = ttk.Label(
    header,
    text="Bluetooth upravljanje 3-sajlnim SpiRob grapplerom preko HC-06 modula",
    style="Subtitle.TLabel"
)
subtitle.pack(anchor="w", pady=(4, 0))


# CONTENT
content = ttk.Frame(main, style="Main.TFrame")
content.pack(fill="both", expand=True)

left = ttk.Frame(content, style="Card.TFrame")
left.pack(side="left", fill="y", padx=(0, 16))

right = ttk.Frame(content, style="Card.TFrame")
right.pack(side="right", fill="both", expand=True)


# LEFT CARD
left_inner = ttk.Frame(left, style="Card.TFrame")
left_inner.pack(fill="both", expand=True, padx=18, pady=18)

ttk.Label(left_inner, text="Konekcija", style="CardTitle.TLabel").pack(anchor="w")

status_text = ttk.Label(left_inner, text="Nije povezano", style="Status.TLabel")
status_text.pack(anchor="w", pady=(8, 16))

ttk.Label(left_inner, text="COM port", style="Normal.TLabel").pack(anchor="w")

port_var = tk.StringVar()
port_combo = ttk.Combobox(left_inner, textvariable=port_var, width=22, state="readonly")
port_combo.pack(anchor="w", pady=(6, 10))

ttk.Button(left_inner, text="Osvježi portove", style="Secondary.TButton", command=refresh_ports).pack(fill="x", pady=4)

connect_btn = ttk.Button(left_inner, text="Poveži", style="Primary.TButton", command=connect)
connect_btn.pack(fill="x", pady=(14, 4))

disconnect_btn = ttk.Button(left_inner, text="Prekini vezu", style="Danger.TButton", command=disconnect)
disconnect_btn.pack(fill="x", pady=4)
disconnect_btn.config(state="disabled")

ttk.Separator(left_inner).pack(fill="x", pady=18)

ttk.Label(left_inner, text="Informacije", style="CardTitle.TLabel").pack(anchor="w")

info = (
    "Baud rate: 9600\n"
    "Modul: HC-06\n"
    "Arduino RX: D10\n"
    "Arduino TX: D11\n"
    "Servo 1: D6\n"
    "Servo 2: D5"
)

ttk.Label(left_inner, text=info, style="Normal.TLabel", justify="left").pack(anchor="w", pady=(8, 0))


# RIGHT CARD
right_inner = ttk.Frame(right, style="Card.TFrame")
right_inner.pack(fill="both", expand=True, padx=18, pady=18)

ttk.Label(right_inner, text="Upravljanje", style="CardTitle.TLabel").pack(anchor="w")

command_status = ttk.Label(
    right_inner,
    text="Zadnja komanda: nema",
    style="Normal.TLabel"
)
command_status.pack(anchor="w", pady=(6, 16))


button_grid = ttk.Frame(right_inner, style="Card.TFrame")
button_grid.pack(fill="x")

control_buttons = []

btn_grab = ttk.Button(
    button_grid,
    text="UHVATI",
    style="Primary.TButton",
    command=lambda: send("g", "Uhvati / start sekvence")
)
btn_grab.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
control_buttons.append(btn_grab)

btn_stop = ttk.Button(
    button_grid,
    text="PUSTI / STOP",
    style="Danger.TButton",
    command=lambda: send("f", "Pusti / stop")
)
btn_stop.grid(row=0, column=1, sticky="ew", padx=6, pady=6)
control_buttons.append(btn_stop)

btn_home = ttk.Button(
    button_grid,
    text="HOME",
    style="Secondary.TButton",
    command=lambda: send("h", "Home pozicija")
)
btn_home.grid(row=1, column=0, sticky="ew", padx=6, pady=6)
control_buttons.append(btn_home)

btn_open = ttk.Button(
    button_grid,
    text="OTVORI",
    style="Secondary.TButton",
    command=lambda: send("o", "Otvori grappler")
)
btn_open.grid(row=1, column=1, sticky="ew", padx=6, pady=6)
control_buttons.append(btn_open)

btn_close = ttk.Button(
    button_grid,
    text="ZATEGNI",
    style="Secondary.TButton",
    command=lambda: send("c", "Zategni grappler")
)
btn_close.grid(row=2, column=0, sticky="ew", padx=6, pady=6)
control_buttons.append(btn_close)

btn_test1 = ttk.Button(
    button_grid,
    text="TEST SERVO 1",
    style="Secondary.TButton",
    command=lambda: send("1", "Test servo 1")
)
btn_test1.grid(row=2, column=1, sticky="ew", padx=6, pady=6)
control_buttons.append(btn_test1)

btn_test2 = ttk.Button(
    button_grid,
    text="TEST SERVO 2",
    style="Secondary.TButton",
    command=lambda: send("2", "Test servo 2")
)
btn_test2.grid(row=3, column=0, columnspan=2, sticky="ew", padx=6, pady=6)
control_buttons.append(btn_test2)

button_grid.columnconfigure(0, weight=1)
button_grid.columnconfigure(1, weight=1)

enable_controls(False)

ttk.Separator(right_inner).pack(fill="x", pady=18)

ttk.Label(right_inner, text="Komunikacijski log", style="CardTitle.TLabel").pack(anchor="w")

log_frame = tk.Frame(right_inner, bg="#020617")
log_frame.pack(fill="both", expand=True, pady=(8, 0))

log_box = tk.Text(
    log_frame,
    bg="#020617",
    fg="#d1d5db",
    insertbackground="white",
    font=("Consolas", 10),
    relief="flat",
    wrap="word",
    height=12
)
log_box.pack(side="left", fill="both", expand=True)

scroll = ttk.Scrollbar(log_frame, command=log_box.yview)
scroll.pack(side="right", fill="y")

log_box.config(yscrollcommand=scroll.set)


# START
refresh_ports()
auto_read()

log("Aplikacija pokrenuta.")
log("Izaberi HC-06 COM port i klikni Poveži.")

root.mainloop()