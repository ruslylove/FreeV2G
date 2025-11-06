import _tkinter # If this fails your Python may not be configured for Tk
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import json
import threading
import queue
from ev_sim import EvSim
from evse_sim import EvseSim

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.animation as animation

class ToolTip:
    """
    Create a tooltip for a given widget.
    """
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20

        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")

        label = tk.Label(self.tooltip, text=self.text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def leave(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

class SimUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("V2G Simulation")
        self.geometry("800x900")

        self.simulation_thread = None
        self.simulation_instance = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.update_queue = queue.Queue()

        # Plotting attributes
        self.plot_data = {'present_voltage': [], 'present_current': []}
        self.target_voltage = 0
        self.target_current = 0

        self.create_widgets()
        # Create a custom style for the progress bar
        self.style = ttk.Style(self)
        # The theme needs to be set for the style to be applied on some platforms
        self.style.theme_use('default') 
        self.style.configure("battery.Horizontal.TProgressbar", background='red')
        self.after(100, self.process_queue)

    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Configuration Frame ---
        config_frame = ttk.LabelFrame(main_frame, text="Configuration")
        config_frame.pack(fill=tk.X, pady=5)

        # Role selection
        ttk.Label(config_frame, text="Role:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.role_var = tk.StringVar(value="EVSE")
        role_menu = ttk.OptionMenu(config_frame, self.role_var, "EVSE", "EV", "EVSE", command=self.toggle_params)
        role_menu.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)

        # --- Parameters Frame ---
        self.params_frame = ttk.LabelFrame(main_frame, text="Parameters")
        self.params_frame.pack(fill=tk.X, pady=5)
        self.ev_params = {}
        self.evse_params = {}

        # EVSE Parameters
        self.evse_params['max_power_label'] = ttk.Label(self.params_frame, text="EVSE Max Power (W):")
        self.evse_params['max_power'] = ttk.Entry(self.params_frame)
        self.evse_params['max_power'].insert(0, "22000")
        ToolTip(self.evse_params['max_power'], "Set the maximum power the EVSE can provide in Watts.")

        self.evse_params['max_current_label'] = ttk.Label(self.params_frame, text="EVSE Max Current (A):")
        self.evse_params['max_current'] = ttk.Entry(self.params_frame)
        self.evse_params['max_current'].insert(0, "100")
        ToolTip(self.evse_params['max_current'], "Set the maximum current the EVSE can provide in Amperes.")

        self.evse_params['max_voltage_label'] = ttk.Label(self.params_frame, text="EVSE Max Voltage (V):")
        self.evse_params['max_voltage'] = ttk.Entry(self.params_frame)
        self.evse_params['max_voltage'].insert(0, "400")
        ToolTip(self.evse_params['max_voltage'], "Set the maximum voltage the EVSE can provide in Volts.")

        self.evse_params['sim_rate_multiplier_label'] = ttk.Label(self.params_frame, text="Ramping Rate:")
        self.evse_params['sim_rate_multiplier'] = ttk.Entry(self.params_frame)
        self.evse_params['sim_rate_multiplier'].insert(0, "0.01")
        ToolTip(self.evse_params['sim_rate_multiplier'], "The rate at which voltage and current ramp up (e.g., 50 V/s and 50 A/s).")

        # EV Parameters
        self.ev_params['initial_soc_label'] = ttk.Label(self.params_frame, text="Initial SOC (%):")
        self.ev_params['initial_soc'] = ttk.Entry(self.params_frame)
        self.ev_params['initial_soc'].insert(0, "20")
        ToolTip(self.ev_params['initial_soc'], "Set the battery's initial State of Charge (e.g., 20 for 20%).")

        self.ev_params['battery_capacity_label'] = ttk.Label(self.params_frame, text="Battery Capacity (Wh):")
        self.ev_params['battery_capacity'] = ttk.Entry(self.params_frame)
        self.ev_params['battery_capacity'].insert(0, "50000")
        ToolTip(self.ev_params['battery_capacity'], "Set the total capacity of the EV's battery in Watt-hours.")

        self.ev_params['charge_rate_multiplier_label'] = ttk.Label(self.params_frame, text="Charge Rate Multiplier:")
        self.ev_params['charge_rate_multiplier'] = ttk.Entry(self.params_frame)
        self.ev_params['charge_rate_multiplier'].insert(0, "100")
        ToolTip(self.ev_params['charge_rate_multiplier'], "Multiplier to accelerate simulated battery charging rate (e.g., 100 for 100x speed).")

        self.ev_params['soc_progressbar_label'] = ttk.Label(self.params_frame, text="SOC:")
        self.soc_var = tk.DoubleVar()
        self.ev_params['soc_progressbar'] = ttk.Progressbar(self.params_frame, variable=self.soc_var, maximum=100, style="battery.Horizontal.TProgressbar")
        ToolTip(self.ev_params['soc_progressbar'], "Current State of Charge of the EV battery.")

        # --- Plot Frame (initially hidden) ---
        self.plot_frame = ttk.LabelFrame(main_frame, text="Live Charging Data")
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.ax_voltage = self.fig.add_subplot(211)
        self.ax_current = self.fig.add_subplot(212)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill=tk.BOTH, expand=True)

        self.ani = animation.FuncAnimation(self.fig, self.animate_plot, interval=500, blit=False)

        # Adjust layout
        self.fig.tight_layout(pad=3.0)

        self.toggle_params() # Initial layout

        # --- Log Frame ---
        log_frame = ttk.LabelFrame(main_frame, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # --- Control Frame ---
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10, before=log_frame)
        self.run_button = ttk.Button(control_frame, text="Run", command=self.run_simulation)
        self.run_button.pack(side=tk.LEFT, padx=5)
        self.pause_button = ttk.Button(control_frame, text="Pause", command=self.pause_simulation, state=tk.DISABLED)
        self.pause_button.pack(side=tk.LEFT, padx=5)
        self.stop_button = ttk.Button(control_frame, text="Stop", command=self.stop_simulation, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)



    def toggle_params(self, event=None):
        # Hide all parameter widgets first
        for widgets in [self.ev_params, self.evse_params]:
            for widget in widgets.values():
                widget.grid_forget()
        self.plot_frame.pack_forget()

        # Show parameters for the selected role
        role = self.role_var.get()
        if role == "EVSE":
            self.evse_params['max_power_label'].grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
            self.evse_params['max_power'].grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)
            self.evse_params['max_current_label'].grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
            self.evse_params['max_current'].grid(row=1, column=1, padx=5, pady=2, sticky=tk.W)
            self.evse_params['max_voltage_label'].grid(row=2, column=0, padx=5, pady=2, sticky=tk.W)
            self.evse_params['max_voltage'].grid(row=2, column=1, padx=5, pady=2, sticky=tk.W)
            self.evse_params['sim_rate_multiplier_label'].grid(row=3, column=0, padx=5, pady=2, sticky=tk.W)
            self.evse_params['sim_rate_multiplier'].grid(row=3, column=1, padx=5, pady=2, sticky=tk.W)
        elif role == "EV":
            self.ev_params['initial_soc_label'].grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
            self.ev_params['initial_soc'].grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)
            self.ev_params['battery_capacity_label'].grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
            self.ev_params['battery_capacity'].grid(row=1, column=1, padx=5, pady=2, sticky=tk.W)
            self.ev_params['charge_rate_multiplier_label'].grid(row=2, column=0, padx=5, pady=2, sticky=tk.W)
            self.ev_params['charge_rate_multiplier'].grid(row=2, column=1, padx=5, pady=2, sticky=tk.W)
            self.ev_params['soc_progressbar_label'].grid(row=3, column=0, padx=5, pady=5, sticky=tk.W)
            self.ev_params['soc_progressbar'].grid(row=3, column=1, padx=5, pady=5, sticky=tk.W+tk.E)

        if role == "EVSE":
            self.plot_frame.pack(fill=tk.BOTH, expand=True, pady=5, after=self.params_frame)

    def log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def get_soc_color(self, soc):
        """Calculates color based on SOC value (Red -> Yellow -> Green)."""
        soc = max(0, min(100, soc))
        if soc <= 50:
            # Red to Yellow
            r = 255
            g = int(255 * (soc / 50))
        else:
            # Yellow to Green
            r = int(255 * (1 - (soc - 50) / 50))
            g = 255
        b = 0
        return f'#{r:02x}{g:02x}{b:02x}'

    def process_queue(self):
        try:
            while True:
                message = self.update_queue.get_nowait()
                if isinstance(message, dict) and 'plot_data' in message:
                    data = message['plot_data']
                    self.plot_data['present_voltage'].append(data['present_voltage'])
                    self.plot_data['present_current'].append(data['present_current'])
                    # Keep the data list from growing indefinitely
                    if len(self.plot_data['present_voltage']) > 100:
                        self.plot_data['present_voltage'].pop(0)
                        self.plot_data['present_current'].pop(0)
                    self.target_voltage = data['target_voltage']
                    self.target_current = data['target_current']
                elif isinstance(message, str) and message.startswith("SOC_UPDATE:"):
                    try:
                        soc_value = float(message.split(":")[1])
                        self.style.configure("battery.Horizontal.TProgressbar", background=self.get_soc_color(soc_value))
                        self.soc_var.set(soc_value)
                    except (IndexError, ValueError):
                        self.log(f"[UI] Invalid SOC update message: {message}")
                else:
                    self.log(str(message))
        except queue.Empty:
            pass
        self.after(100, self.process_queue)

    def animate_plot(self, i):
        if self.role_var.get() != "EVSE" or not self.simulation_thread or not self.simulation_thread.is_alive():
            return

        # Voltage Plot
        self.ax_voltage.clear()
        self.ax_voltage.plot(self.plot_data['present_voltage'], label='Present Voltage (V)', color='blue')
        if self.simulation_instance:
            max_v = self.simulation_instance.charger.getEvseMaxVoltage()
            self.ax_voltage.axhline(y=max_v, color='red', linestyle='--', label=f'Max Voltage ({max_v}V)')
            self.ax_voltage.axhline(y=self.target_voltage, color='green', linestyle='--', label=f'Target Voltage ({self.target_voltage}V)')
        self.ax_voltage.set_title("Voltage")
        self.ax_voltage.set_ylabel("Voltage (V)")
        self.ax_voltage.legend(loc='upper left')
        self.ax_voltage.grid(True)

        # Current Plot
        self.ax_current.clear()
        self.ax_current.plot(self.plot_data['present_current'], label='Present Current (A)', color='orange')
        if self.simulation_instance:
            max_c = self.simulation_instance.charger.getEvseMaxCurrent()
            self.ax_current.axhline(y=max_c, color='red', linestyle='--', label=f'Max Current ({max_c}A)')
            self.ax_current.axhline(y=self.target_current, color='green', linestyle='--', label=f'Target Current ({self.target_current}A)')
        self.ax_current.set_title("Current")
        self.ax_current.set_ylabel("Current (A)")
        self.ax_current.legend(loc='upper left')
        self.ax_current.grid(True)

    def run_simulation(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

        self.style.configure("battery.Horizontal.TProgressbar", background='red')
        self.soc_var.set(0) # Reset progress bar
        self.stop_event.clear()
        self.pause_event.clear()

        # Reset plot data
        self.plot_data = {'present_voltage': [], 'present_current': []}
        self.target_voltage = 0
        self.target_current = 0

        role = self.role_var.get()
        host = '127.0.0.1'
        port = 65432

        try:
            if role == "EV":
                initial_soc = int(self.ev_params['initial_soc'].get())
                self.style.configure("battery.Horizontal.TProgressbar", background=self.get_soc_color(initial_soc))
                self.simulation_instance = EvSim(host, port, self.update_queue, self.stop_event, self.pause_event)
                self.soc_var.set(int(self.ev_params['initial_soc'].get()))
                self.simulation_instance.battery.setSOC(int(self.ev_params['initial_soc'].get()))
                self.simulation_instance.battery.setCapacity(int(self.ev_params['battery_capacity'].get()))
                self.simulation_instance.battery.charge_rate_multiplier = float(self.ev_params['charge_rate_multiplier'].get())
            else: # EVSE
                self.simulation_instance = EvseSim(host, port, self.update_queue, self.stop_event, self.pause_event)
                ramping_rate = float(self.evse_params['sim_rate_multiplier'].get())
                # Set the ramp-up rates for voltage and current
                self.simulation_instance.charger.setEvseDeltaVoltage(ramping_rate)
                self.simulation_instance.charger.setEvseDeltaCurrent(ramping_rate)
                self.simulation_instance.charger.setEvseMaxPower(int(self.evse_params['max_power'].get()))
                self.simulation_instance.charger.setEvseMaxCurrent(int(self.evse_params['max_current'].get()))
                self.simulation_instance.charger.setEvseMaxVoltage(int(self.evse_params['max_voltage'].get()))
                self.simulation_instance.charger.sim_rate_multiplier = 1.0 # Set to 1 as rate is now controlled by delta
        except ValueError as e:
            messagebox.showerror("Invalid Input", f"Please check your parameters. Error: {e}")
            return

        self.simulation_thread = threading.Thread(target=self.simulation_instance.loop)
        self.simulation_thread.daemon = True
        self.simulation_thread.start()

        self.run_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL)

    def pause_simulation(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_button.config(text="Pause")
            self.log("--- Simulation Resumed ---")
        else:
            self.pause_event.set()
            self.pause_button.config(text="Resume")
            self.log("--- Simulation Paused ---")

    def stop_simulation(self):
        if self.simulation_thread and self.simulation_thread.is_alive():
            self.stop_event.set()
            # If paused, unpause it to allow the loop to see the stop_event
            if self.pause_event.is_set():
                self.pause_event.clear()
            
            # Wait for the thread to finish
            self.simulation_thread.join(timeout=2.0)
            if self.simulation_thread.is_alive():
                self.log("[UI] Warning: Simulation thread did not stop gracefully.")

        self.log("--- Simulation Stopped by User ---")
        self.run_button.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.DISABLED, text="Pause")
        self.stop_button.config(state=tk.DISABLED)
        self.simulation_thread = None
        self.simulation_instance = None

    def on_closing(self):
        if self.simulation_thread and self.simulation_thread.is_alive():
            self.stop_simulation()
        self.destroy()


def redirect_stdout(q):
    """A helper class to redirect stdout to a queue."""
    class StdoutRedirector:
        def __init__(self, queue):
            self.queue = queue

        def write(self, string):
            self.queue.put(string.strip())

        def flush(self):
            pass # No-op
    
    import sys
    sys.stdout = StdoutRedirector(q)
    sys.stderr = StdoutRedirector(q)


if __name__ == "__main__":
    app = SimUI()
    # Redirect print statements to the UI log
    redirect_stdout(app.update_queue)
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()