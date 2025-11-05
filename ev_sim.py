import time
import socket
import json
from battery_sim import BatterySim

def send_message(conn, msg_id, data):
    """Sends a message over the socket."""
    message = json.dumps({'id': msg_id, 'data': data}).encode('utf-8')
    conn.sendall(len(message).to_bytes(4, 'big') + message)
    print(f"[EV_SIM] SENT: id={hex(msg_id)}, data={data}")

def receive_message(conn):
    """Receives a message from the socket."""
    raw_msglen = conn.recv(4)
    if not raw_msglen:
        return None, None
    msglen = int.from_bytes(raw_msglen, 'big')
    data = conn.recv(msglen)
    message = json.loads(data.decode('utf-8'))
    print(f"[EV_SIM] RECV: id={hex(message['id'])}, data={message['data']}")
    return message['id'], message['data']

class EvSim:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.battery = BatterySim()
        self.config = {
            "evid": "C49300222222",
            "protocol_count": 2,
            "protocols": [0, 1],
            "payment_method_count": 1,
            "payment_method": [0],
            "energy_transfer_mode_count": 1,
            "energy_transfer_mode": [0], # DC
            "battery_capacity": self.battery.getCapacity()
        }
        self.charging_params = {}
        self._update_charging_parameter()
        self.schedule = None
        self.current_energy_transfer_mode = -1
        self.state = "init"
        self.conn = None
        self.charge_loop_interval = 2.0 # Default interval in seconds

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.conn:
            self.conn.close()

    def load(self, configDict):
        if "battery" in configDict:
            for key, value in configDict["battery"].items():
                if hasattr(self.battery, key):
                    setattr(self.battery, key, value)
        if "ev" in configDict:
            for key, value in configDict["ev"].items():
                self.config[key] = value
        self._update_charging_parameter()

    def _update_charging_parameter(self):
        self.charging_params = {
            "max_voltage": self.battery.max_voltage,
            "max_current": self.battery.max_current,
            "max_power": self.battery.max_power,
            "soc": self.battery.getSOC(),
            "target_voltage": self.battery.target_voltage,
            "target_current": self.battery.target_current,
        }

    def _initialize(self):
        """Initializes the EV simulation and connects to EVSE."""
        print("[EV_SIM] Initializing...")
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn.connect((self.host, self.port))
        print(f"[EV_SIM] Connected to EVSE at {self.host}:{self.port}")

    def _handle_evse_messages(self):
        """Handles messages from the EVSE."""
        charge_loop_count = 0
        # Start by indicating readiness for V2G
        send_message(self.conn, 0x1000, {}) # EV ready for V2G

        while self.state != "end":
            try:
                msg_id, data = receive_message(self.conn)
                if msg_id is None:
                    print("[EV_SIM] EVSE disconnected.")
                    self.state = "end"
                    break

                # If we are in the charging state, we need to handle the charge loop
                if self.state == "charging":
                    if msg_id == 0x85: # This is the expected response in the charge loop

                        # Check if we should stop charging
                        if charge_loop_count > 3 and self.battery.getSOC() >= 80:
                            print("[EV_SIM] Target SOC reached. Requesting to stop charging.")
                            send_message(self.conn, 0x1004, {}) # Request stop charging
                            self.state = "stopping"
                            continue

                        # 1. Handle the new parameters from the EVSE
                        self._handle_dc_charge_parameters_changed(data)
                        charge_loop_count += 1
                        
                        # 2. Update battery SOC based on the new parameters and elapsed time
                        self.battery.tickSimulation()
                        self._update_charging_parameter()
                        print(f"[EV_SIM] >> Charge Loop {charge_loop_count} | Battery SOC: {self.battery.getSOC()}% <<")

                        # 3. Wait before sending the next update
                        print(f"[EV_SIM] Waiting for {self.charge_loop_interval} seconds...")
                        time.sleep(self.charge_loop_interval)

                        # 4. Send the next charge loop update to the EVSE
                        send_message(self.conn, 0x1005, self.charging_params)
                        continue # Continue to next loop iteration to wait for the next 0x85 message

                if msg_id == 0x80: # SessionStarted
                    self._handle_session_started(data)
                elif msg_id == 0x82: # AuthorizationStatus
                    self._handle_authorization_status(data)
                elif msg_id == 0x84: # Schedules
                    self._handle_schedules(data)
                elif msg_id == 0x89: # StartCharging
                    self._handle_start_charging(data)
                elif msg_id == 0x8A: # StopCharging
                    self._handle_stop_charging(data)
                elif msg_id == 0x8C: # SessionStopped
                    self._handle_session_stopped(data)
                else:
                    print(f"[EV_SIM] Unknown message ID: {hex(msg_id)}")

            except (ConnectionResetError, BrokenPipeError):
                print("[EV_SIM] Connection lost with EVSE.")
                self.state = "end"
                break

    def _handle_session_started(self, data):
        print("[EV_SIM] 'Session Started' received.")
        time.sleep(2)
        self.current_energy_transfer_mode = data.get('energy_transfer_mode', -1)
        if self.current_energy_transfer_mode != -1:
            self.battery.setEnergyTransferMode(self.current_energy_transfer_mode)
            print(f"[EV_SIM] Energy transfer mode set to: {self.current_energy_transfer_mode}")
        else:
            print("[EV_SIM] Warning: Energy transfer mode not provided by EVSE.")
        self.state = "session_started"
        # Request authorization
        send_message(self.conn, 0x1001, {})

    def _handle_authorization_status(self, data):
        if data.get('authorized'):
            print("[EV_SIM] Authorization granted.")
            time.sleep(2)
            self.state = "authorized"
            # Send charging parameters
            self._update_charging_parameter()
            send_message(self.conn, 0x1002, self.charging_params)
        else:
            print("[EV_SIM] Authorization denied. Stopping session.")
            self.state = "end"
            send_message(self.conn, 0x1006, {}) # Stop session

    def _handle_schedules(self, data):
        print("[EV_SIM] 'Schedules' received.")
        time.sleep(2)
        self.schedule = data
        self.state = "schedule_received"
        # Request to start charging
        send_message(self.conn, 0x1003, {})

    def _handle_start_charging(self, data):
        print("[EV_SIM] 'Start Charging' confirmed by EVSE.")
        time.sleep(2)
        self.battery.startCharging()
        self.state = "charging"
        # Send the first charge loop update to kick off the process
        send_message(self.conn, 0x1005, self.charging_params)

    def _handle_stop_charging(self, data):
        print("[EV_SIM] 'Stop Charging' confirmed by EVSE.")
        self.state = "stopped"
        time.sleep(2)
        self.battery.is_charging = False
        send_message(self.conn, 0x1006, {}) # Stop session

    def _handle_dc_charge_parameters_changed(self, data):
        print("[EV_SIM] Received EVSE charge parameters update.")
        self.battery.in_voltage = data.get('present_voltage', 0)
        self.battery.in_current = data.get('present_current', 0)

    def _handle_session_stopped(self, data):
        print("[EV_SIM] 'Session Stopped' received from EVSE.")
        self.state = "end"

    def loop(self):
        """
        This will handle a complete charging session of the EV simulation.
        """
        try:
            self._initialize()
            
            # Simulate SLAC
            print("[EV_SIM] Simulating SLAC matching...")
            time.sleep(2)
            print("[EV_SIM] SLAC matching successful.")

            # Handle V2G communication
            self._handle_evse_messages()

        except KeyboardInterrupt:
            print("\n[EV_SIM] Shutting down.")
        except Exception as e:
            print(f"[EV_SIM] An error occurred: {e}")
        finally:
            if self.conn:
                self.conn.close()
            print("[EV_SIM] EV loop finished.")