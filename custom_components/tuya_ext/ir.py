from homeassistant.backports.enum import StrEnum
from homeassistant.components.climate import HVACMode


class IR_DPCODE(StrEnum):
    """Data Point Codes used by wifi ir's.
    https://developer.tuya.com/en/docs/iot/standarddescription?id=K9i5ql6waswzq
    """

    # climate ir functions
    MODE = "M"  # ac function mode M ENUM 1-4
    POWERON = "PowerOn"  # ac function PowerOn   -> STRING "PowerOn"
    POWEROFF = "PowerOff"  # ac function PowerOff  -> STRING "PowerOff"
    WIND = "F"  # ac function wind (F) ENUM -> Integer 0-3
    TEMP = "T"  # ac function temp (T) ENUM -> Integer 16-30


class IR_MEDIAREMOTE_DPCODE(StrEnum):
    PLAY = "Play"
    NEXT = "Next"
    PAUSE = "Pause"
    POWEROFF = "PowerOff"
    POWERON = "PowerOn"
    PREVIOUS = "Previous"
    VOLUMEUP = "Volume+"
    VOLUMEDOWN = "Volume-"


# mode (M) climate ir modes
TUYA_HVAC_IR_CLIMATE_CODE_TO_HA = {
    0: HVACMode.COOL,
    1: HVACMode.HEAT,
    2: HVACMode.AUTO,
    3: HVACMode.FAN_ONLY,
    4: HVACMode.DRY,
    5: HVACMode.OFF,
}
TUYA_HVAC_IR_CLIMATE_FAN_CODE_TO_NAME = {0: "auto", 1: "low", 2: "middle", 3: "high"}
