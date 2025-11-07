import socket
import time
from Whitebeet import Whitebeet
from Logger import Logger

HOST = '127.0.0.1'
EV_PORT = 6000

def main():
    """
    Simulates an EV host controller interacting with the Whitebeet.
    Follows the sequence from section 21.9 of the SEVENSTAX manual.
    """
    logger = Logger()
    logger.log("--- EV Simulation Started ---")
    
    try:
        # The Whitebeet class expects an interface type and name.
        # For the stub, we use 'ETH' and the socket details.
        # The 'mac' parameter is not used by the stub but required by the class constructor.
        wb = Whitebeet(iftype='ETH', iface=(HOST, EV_PORT), mac='00:00:00:00:00:01')

        # --- 21.9.1 Configuration ---
        logger.log("EV: Configuring Whitebeet...")
        wb.v2gSetMode(0)  # 0 for EV

        ev_config = {
            "evid": b'\x00\x00\x00\x00\x00\x01',
            "protocol_count": 2,
            "protocols": [0, 1], # DIN and ISO
            "payment_method_count": 1,
            "payment_method": [0], # EIM
            "energy_transfer_mode_count": 1,
            "energy_transfer_mode": [1], # DC Extended
            "battery_capacity": (50, 3) # 50kWh
        }
        wb.v2gEvSetConfiguration(ev_config)
        logger.log("EV: V2G configuration set.")

        dc_params = {
            "min_voltage": 0, "min_current": 0, "min_power": 0,
            "max_voltage": 450, "max_current": 80, "max_power": 30000,
            "soc": 50, "status": 0, "target_voltage": 400, "target_current": 0,
            "full_soc": 100, "bulk_soc": 80, "energy_request": (10, 3), # 10kWh
            "departure_time": 3600
        }
        wb.v2gSetDCChargingParameters(dc_params)
        logger.log("EV: DC charging parameters set.")

        wb.v2gStart()
        logger.log("EV: V2G service started.")

        # --- 21.9.2 Start Session ---
        logger.log("EV: Starting session...")
        wb.v2gStartSession()

        # --- Main Loop: Wait for EVSE responses ---
        session_running = True
        while session_running:
            sub_id, payload = wb.v2gEvReceiveRequest()
            if sub_id is None:
                time.sleep(0.1)
                continue

            logger.log(f"EV: Received notification with Sub-ID: {hex(sub_id)}")

            if sub_id == 0xC0: # SessionStarted
                parsed = wb.v2gEvParseSessionStarted(payload)
                logger.log(f"EV: Session started with EVSEID: {parsed['evse_id'].decode()}")

            elif sub_id == 0xC4: # CableCheckReady
                logger.log("EV: Cable check is ready. Starting cable check...")
                wb.v2gStartCableCheck()

            elif sub_id == 0xC5: # CableCheckFinished
                logger.log("EV: Cable check finished by EVSE.")

            elif sub_id == 0xC6: # PreChargingReady
                logger.log("EV: Pre-charging is ready. Starting pre-charge...")
                wb.v2gStartPreCharging()

            elif sub_id == 0xC7: # ChargingReady
                logger.log("EV: Charging is ready. Starting charge...")
                wb.v2gStartCharging()

            elif sub_id == 0xC8: # ChargingStarted
                logger.log("EV: Charging has started. Entering charge loop for 5 seconds...")
                # --- 21.9.4 Charge Loop ---
                charge_loop_end = time.time() + 5
                while time.time() < charge_loop_end:
                    # In a real scenario, we would send CurrentDemandReq here
                    # and update our parameters based on EVSE response.
                    # For this simulation, we just wait.
                    logger.log("EV: ...charging...")
                    time.sleep(1)
                
                logger.log("EV: Charge loop finished. Stopping charge.")
                wb.v2gStopCharging(renegotiation=False)

            elif sub_id == 0xC9: # ChargingStopped
                logger.log("EV: Charging stopped by EVSE.")

            elif sub_id == 0xCA: # PostChargingReady
                logger.log("EV: Post-charging is ready. Stopping session.")
                wb.v2gStopSession()

            elif sub_id == 0xCB: # SessionStopped
                logger.log("EV: Session stopped successfully.")
                session_running = False # Exit loop
                
            elif sub_id == 0xCD: # SessionError
                parsed = wb.v2gEvParseSessionError(payload)
                logger.log(f"EV: Session Error! Code: {parsed['code']}. Stopping.")
                session_running = False

    except ConnectionError as e:
        logger.log(f"EV: Connection Error: {e}")
    except Warning as w:
        logger.log(f"EV: Warning: {w}")
    except KeyboardInterrupt:
        logger.log("\nEV: Simulation stopped by user.")
    except Exception as e:
        logger.log(f"EV: An unexpected error occurred: {e}")
    finally:
        logger.log("--- EV Simulation Finished ---")

if __name__ == "__main__":
    main()