MESSAGE_IDS = {
    # EVSE to EV (0x80 - 0xFF)
    0x80: "SessionStarted",
    0x6C: "SetSchedules", # Per documentation, this is the command to send schedules
    0x82: "AuthorizationStatus",
    0x84: "SchedulesRequested", # Status message from EVSE to host
    0x85: "DCChargeParametersChanged",
    0x89: "StartCharging",
    0x8A: "StopCharging",
    0x8C: "SessionStopped",

    # EV to EVSE (0x1000 - 0x10FF)
    0x1000: "EVReadyForV2G",
    0x1001: "RequestAuthorization",
    0x1002: "ChargeParameters",
    0x1003: "RequestStartCharging",
    0x1004: "RequestStopCharging",
    0x1005: "ChargeLoopUpdate",
    0x1006: "SessionStop",
}

def get_message_name(msg_id):
    """
    Returns the name of a message from its ID.
    If not found, returns 'Unknown'.
    """
    return MESSAGE_IDS.get(msg_id, "Unknown")