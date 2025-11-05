import argparse
import json
from evse_sim import EvseSim
from ev_sim import EvSim

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Codico Whitebeet simulation.')
    parser.add_argument('-r', '--role', type=str, choices=('EVSE', 'EV'), required=True, help='This is the role for the simulation. "EV" for EV mode and "EVSE" for EVSE mode')
    parser.add_argument('-c', '--config', type=str, help='Path to configuration file for EV. Defaults to ./ev.json.', nargs='?', const="./ev.json")
    parser.add_argument('--host', type=str, default='127.0.0.1', help='Host for TCP/IP simulation connection.')
    parser.add_argument('--port', type=int, default=65432, help='Port for TCP/IP simulation connection.')

    # EV specific arguments
    parser.add_argument('--ev-initial-soc', type=int, default=20, help='Initial State of Charge (SOC) for the EV battery (0-100).')
    parser.add_argument('--ev-battery-capacity', type=int, default=50000, help='Total capacity of the EV battery in Wh.')
    # EVSE specific arguments
    parser.add_argument('--evse-max-voltage', type=int, default=400, help='EVSE maximum voltage.')
    parser.add_argument('--evse-max-current', type=int, default=100, help='EVSE maximum current.')
    parser.add_argument('--evse-max-power', type=int, default=25000, help='EVSE maximum power.')
    
    args = parser.parse_args()

    print(f'Welcome to Codico Whitebeet {args.role} simulation')

    if args.role == "EV":
        config = None
        if args.config:
            try:
                with open(args.config, 'r') as configFile:
                    config = json.load(configFile)
            except FileNotFoundError:
                print(f"Configuration file {args.config} not found. Using default configuration.")
        
        with EvSim(args.host, args.port) as ev:
            if config:
                print(f"EV configuration: {config}")
                ev.load(config)
            # Override with command-line arguments if provided
            ev.battery.setSOC(args.ev_initial_soc)
            ev.battery.setCapacity(args.ev_battery_capacity)
            ev.loop()
            print("EV simulation finished")

    elif args.role == 'EVSE':
        with EvseSim(args.host, args.port) as evse:
            # Set regulation parameters of the charger
            evse.charger.setEvseDeltaVoltage(0.5)
            evse.charger.setEvseDeltaCurrent(0.05)

            # Set limitations of the charger
            evse.charger.setEvseMaxVoltage(args.evse_max_voltage)
            evse.charger.setEvseMaxCurrent(args.evse_max_current)
            evse.charger.setEvseMaxPower(args.evse_max_power)

            # Start the EVSE loop
            evse.loop()
            print("EVSE simulation finished")

    print("Goodbye!")