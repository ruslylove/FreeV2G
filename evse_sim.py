import socket
import time
from Whitebeet import Whitebeet
from Logger import Logger

HOST = '127.0.0.1'
EVSE_PORT = 6001

def main():
    """
    Simulates an EVSE host controller interacting with the Whitebeet.
    Follows the sequence from section 21.8 of the SEVENSTAX manual.
    """
    logger = Logger()
    logger.log("--- EVSE Simulation Started ---")

    try:
        # The Whitebeet class expects an interface type and name.
        # For the stub, we use 'ETH' and the socket details.
        # The 'mac' parameter is not used by the stub but required by the class constructor.
        wb = Whitebeet(iftype='SIM', iface=(HOST, EVSE_PORT), mac='00:00:00:00:00:02')

        # --- 21.8.1 Configuration ---
        logger.log("EVSE: Configuring Whitebeet...")
        wb.v2gSetMode(1)  # 1 for EVSE
        
        evse_config = {
            'evse_id_DIN': "+49*123*456*789",
            'evse_id_ISO': "DE*A23*E45B*78C",
            'protocol': [0, 1],  # DIN and ISO
            'payment_method': [0, 1], # EIM and PNC
            'energy_transfer_mode': [1], # DC Extended
            'certificate_installation_support': False,
            'certificate_update_support': False
        }
        wb.v2gEvseSetConfiguration(evse_config)
        logger.log("EVSE: V2G configuration set.")

        dc_params = {
            'isolation_level': 0, # Invalid
            'min_voltage': 0,
            'min_current': 0,
            'max_voltage': 400,
            'max_current': 50,
            'max_power': 20000,
            'peak_current_ripple': (5, -1), # 0.5A
            'status': 0 # Ready
        }
        wb.v2gEvseSetDcChargingParameters(dc_params)
        logger.log("EVSE: DC charging parameters set.")

        wb.v2gStart()
        logger.log("EVSE: V2G service started.")
        wb.v2gEvseStartListen()
        logger.log("EVSE: Listening for EV...")

        # --- Main Loop: Handle EV Requests (21.8.2 onwards) ---
        while True:
            sub_id, payload = wb.v2gEvseReceiveRequestSilent()
            if sub_id is None:
                time.sleep(0.2)
                continue

            logger.log(f"EVSE: Received request with Sub-ID: {hex(sub_id)}")

            if sub_id == 0x80: # SessionStarted
                parsed_data = wb.v2gEvseParseSessionStarted(payload)
                logger.log(f"EVSE: Session Started with EVCCID: {parsed_data['evcc_id'].hex()}")

            elif sub_id == 0x82: # AuthorizationStatusRequested
                logger.log("EVSE: Authorization requested. Authorizing...")
                time.sleep(1) # Simulate checking
                wb.v2gEvseSetAuthorizationStatus(True)
                logger.log("EVSE: Authorization granted.")

            elif sub_id == 0x84: # SchedulesRequested
                logger.log("EVSE: Schedules requested. Sending schedule...")
                schedules = {
                    'code': 0, # OK
                    'schedule_tuples': [{
                        'schedule_tuple_id': 1,
                        'schedules': [{
                            'start': 0,
                            'interval': 3600,
                            'power': (22, 3) # 22kW
                        }]
                    }]
                }
                wb.v2gEvseSetSchedules(schedules)
                logger.log("EVSE: Schedules sent.")

            elif sub_id == 0x87: # CableCheckRequested
                logger.log("EVSE: Cable check requested. Simulating check...")
                time.sleep(2) # Simulate cable check
                wb.v2gEvseSetCableCheckFinished(True)
                logger.log("EVSE: Cable check finished.")

            elif sub_id == 0x88: # PreChargeStarted
                logger.log("EVSE: Pre-charge started by EV. Updating DC params...")
                update_params = {
                    'isolation_level': 1, # Valid
                    'present_voltage': (380, 0),
                    'present_current': (0,0),
                    'status': 0 # Ready
                }
                wb.v2gEvseUpdateDcChargingParameters(update_params)
                logger.log("EVSE: DC params updated for pre-charge.")

            elif sub_id == 0x89: # StartChargingRequested
                logger.log("EVSE: Start charging requested. Starting...")
                wb.v2gEvseStartCharging()
                logger.log("EVSE: Charging started.")

            elif sub_id == 0x85: # DCChargeParametersChanged (during charge loop)
                logger.log("EVSE: Received EV charge parameters. Updating EVSE state...")
                update_params = {
                    'isolation_level': 1, # Valid
                    'present_voltage': (400, 0),
                    'present_current': (25, 0), # Providing 25A
                    'status': 0 # Ready
                }
                wb.v2gEvseUpdateDcChargingParameters(update_params)
                logger.log("EVSE: Charge loop params updated.")

            elif sub_id == 0x8A: # StopChargingRequested
                logger.log("EVSE: Stop charging requested. Stopping...")
                wb.v2gEvseStopCharging()
                logger.log("EVSE: Charging stopped.")

            elif sub_id == 0x8C: # SessionStopped
                logger.log("EVSE: Session stopped by EV. Shutting down listener.")
                wb.v2gEvseStopListen()
                logger.log("EVSE: Listener stopped. Session finished.")
                break # End simulation

    except ConnectionError as e:
        logger.log(f"EVSE: Connection Error: {e}")
    except Warning as w:
        logger.log(f"EVSE: Warning: {w}")
    except KeyboardInterrupt:
        logger.log("\nEVSE: Simulation stopped by user.")
    except Exception as e:
        logger.log(f"EVSE: An unexpected error occurred: {e}")
    finally:
        logger.log("--- EVSE Simulation Finished ---")

if __name__ == "__main__":
    main()