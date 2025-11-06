import time
import socket
import threading
import json
from Charger_sim import ChargerSim
from message_ids import get_message_name

def send_message(conn, msg_id, data):
    """Sends a message over the socket."""
    message = json.dumps({'id': msg_id, 'data': data}).encode('utf-8')
    conn.sendall(len(message).to_bytes(4, 'big') + message)
    msg_name = get_message_name(msg_id)
    print(f"[EVSE_SIM] SENT: {msg_name} (id={hex(msg_id)}), data={data}")

def receive_message(conn):
    """Receives a message from the socket."""
    raw_msglen = conn.recv(4)
    if not raw_msglen:
        return None, None
    msglen = int.from_bytes(raw_msglen, 'big')
    data = conn.recv(msglen)
    message = json.loads(data.decode('utf-8'))
    msg_id = message['id']
    msg_name = get_message_name(msg_id)
    print(f"[EVSE_SIM] RECV: {msg_name} (id={hex(msg_id)}), data={message['data']}")
    return msg_id, message['data']

class EvseSim:
    def __init__(self, host, port, update_queue=None, stop_event=None, pause_event=None):
        self.host = host
        self.port = port
        self.charger = ChargerSim()
        self.schedule = None
        self.evse_config = None
        self.charging = False
        self.update_queue = update_queue
        self.stop_event = stop_event or threading.Event()
        self.pause_event = pause_event or threading.Event()
        self.conn = None
        self.sock = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.conn:
            self.conn.close()
        if self.sock:
            self.sock.close()

    def _initialize(self):
        """Initializes the EVSE simulation."""
        print("[EVSE_SIM] Initializing...")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((self.host, self.port))
        self.sock.listen()
        print(f"[EVSE_SIM] Waiting for EV connection on {self.host}:{self.port}")
        self.conn, addr = self.sock.accept()
        print(f"[EVSE_SIM] EV connected from {addr}")

    def _handle_ev_requests(self):
        """Handles requests from the EV."""
        self.evse_config = {
            "evse_id_DIN": '+49*123*456*789',
            "evse_id_ISO": 'DE*A23*E45B*78C',
            "protocol": [0, 1], 
            "payment_method": [0],
            "energy_transfer_mode": [0, 1, 2, 3, 4, 5],
        }
        
        # Simulate SessionStarted
        session_started_data = {
            'protocol': 2,
            'session_id': 'f3976451aedd64ce',
            'evcc_id': '000101637730',
            'energy_transfer_mode': 0 # Default to DC
        }
        send_message(self.conn, 0x80, session_started_data)

        while not self.stop_event.is_set():
            # Handle pause
            if self.pause_event.is_set():
                time.sleep(0.5)
                continue

            self.conn.settimeout(0.5) # Use a timeout to remain responsive
            try:
                msg_id, data = receive_message(self.conn)
                if msg_id is None:
                    print("[EVSE_SIM] EV disconnected.")
                    break

                if msg_id == 0x1000: # EV ready for V2G
                    self._handle_v2g_ready(data)
                elif msg_id == 0x1001: # EV requests authorization
                    self._handle_request_authorization(data)
                elif msg_id == 0x1002: # EV sends charging parameters
                    self._handle_charge_parameters(data)
                elif msg_id == 0x1003: # EV requests start charging
                    self._handle_request_start_charging(data)
                elif msg_id == 0x1004: # EV requests stop charging
                    self._handle_request_stop_charging(data)
                elif msg_id == 0x1005: # EV sends charge loop update
                    self._handle_charge_loop_update(data)
                elif msg_id == 0x1006: # EV session stop
                    print("[EVSE_SIM] Session stop requested by EV.")
                    send_message(self.conn, 0x8C, {'closure_type': 0}) # SessionStopped
                    break
                else:
                    print(f"[EVSE_SIM] Unknown message ID: {hex(msg_id)}")
            except socket.timeout:
                continue # No message received, loop again

            except (ConnectionResetError, BrokenPipeError):
                print("[EVSE_SIM] Connection lost with EV.")
                break

    def _handle_v2g_ready(self, data):
        print("[EVSE_SIM] EV is ready for V2G communication.")
        time.sleep(2)
        # EV is ready, we can proceed.

    def _handle_request_authorization(self, data):
        print("[EVSE_SIM] 'Request Authorization' received")
        # In a real UI, this would be handled differently, but for now, auto-authorize.
        if self.update_queue:
             self.update_queue.put("[UI ACTION] Auto-authorizing vehicle.")
        auth_str = "yes"
        # auth_str = input("Authorize the vehicle? Type 'yes' or 'no': ")
        authorized = auth_str.lower() == "yes"
        if authorized:
            print("[EVSE_SIM] Vehicle was authorized by user!")
        else:
            print("[EVSE_SIM] Vehicle was NOT authorized by user!")
        send_message(self.conn, 0x82, {'authorized': authorized})

    def _handle_charge_parameters(self, data):
        print("[EVSE_SIM] Received charge parameters from EV.")
        time.sleep(2)

        # Set the EV's initial requested parameters on the charger
        target_voltage = data.get('target_voltage', 0)
        target_current = data.get('target_current', 0)
        self.charger.setEvTargetVoltage(target_voltage)
        self.charger.setEvTargetCurrent(target_current)
        print(f"[EVSE_SIM] Initial EV targets set: Voltage={target_voltage}V, Current={target_current}A")

        # Per the HCI spec, the EVSE first notifies the host that schedules are requested.
        # We simulate this by logging it.
        schedules_requested_status = {'timeout': 500, 'max_entries': 5}
        print(f"[EVSE_SIM] STATUS: SchedulesRequested (id=0x84), data={schedules_requested_status}")

        # The host (our simulation) then responds by providing the schedules.
        self.schedule = {
            "code": 0,
            "schedule_tuples": [{
                'schedule_tuple_id': 1,
                'schedules':[
                    {"start": 0, "interval": 3600, "power": self.charger.getEvseMaxPower()},
                    {"start": 3600, "interval": 82800, "power": int(self.charger.getEvseMaxPower() * 0.5)}
                ]
            }]
        }
        print(f"[EVSE_SIM] Sending schedule: {self.schedule}")
        send_message(self.conn, 0x6C, self.schedule) # SetSchedules

    def _handle_request_start_charging(self, data):
        print("[EVSE_SIM] 'Request Start Charging' received")
        time.sleep(2)
        self.charger.start()
        self.charging = True
        send_message(self.conn, 0x89, {}) # StartCharging
        print("[EVSE_SIM] Charging started.")

    def _handle_request_stop_charging(self, data):
        print("[EVSE_SIM] 'Request Stop Charging' received")
        time.sleep(2)
        self.charger.stop()
        self.charging = False
        send_message(self.conn, 0x8A, {}) # StopCharging
        print("[EVSE_SIM] Charging stopped.")

    def _handle_charge_loop_update(self, data):
        soc = data.get('soc')
        print(f"[EVSE_SIM] Charge loop update from EV: SOC={soc}%")
        time.sleep(2)

        # Update charger simulation
        target_voltage = data.get('target_voltage', 0)
        target_current = data.get('target_current', 0)
        self.charger.setEvTargetVoltage(target_voltage)
        self.charger.setEvTargetCurrent(target_current)

        # Let the charger simulation calculate the new present values
        self.charger._calcEvsePresentVoltage()
        self.charger._calcEvsePresentCurrent()

        # Simulate EVSE measurements
        charging_params = {
            'present_voltage': int(self.charger.getEvsePresentVoltage()),
            'present_current': int(self.charger.getEvsePresentCurrent()),
            'max_voltage': int(self.charger.getEvseMaxVoltage()),
            'max_current': int(self.charger.getEvseMaxCurrent()),
            'max_power': int(self.charger.getEvseMaxPower()),
            'status': 0,
        }

        # Send data to UI for plotting
        if self.update_queue:
            plot_data = {
                'present_voltage': charging_params['present_voltage'],
                'present_current': charging_params['present_current'],
                'target_voltage': target_voltage,
                'target_current': target_current,
                'max_voltage': charging_params['max_voltage'],
                'max_current': charging_params['max_current'],
            }
            self.update_queue.put({'plot_data': plot_data})

        # Send updated EVSE charging parameters
        send_message(self.conn, 0x85, charging_params) # DCChargeParametersChanged

    def loop(self):
        """
        This will handle a complete charging session of the EVSE simulation.
        """
        try:
            self._initialize()
            
            # Simulate SLAC and network setup
            print("[EVSE_SIM] Simulating SLAC matching...")
            time.sleep(1)
            print("[EVSE_SIM] SLAC matching successful.")
            
            # Handle V2G communication
            if not self.stop_event.is_set():
                self._handle_ev_requests()

        except KeyboardInterrupt:
            print("\n[EVSE_SIM] Shutting down.")
        except Exception as e:
            print(f"[EVSE_SIM] An error occurred: {e}")
        finally:
            if self.conn:
                self.conn.close()
            if self.sock:
                self.sock.close()
            print("[EVSE_SIM] EVSE loop finished.")