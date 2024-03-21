
from homeassistant.core import HomeAssistant
from homeassistant.components.tuya import HomeAssistantTuyaData
from homeassistant.components.tuya.sensor import SENSORS, TuyaSensorEntityDescription
from homeassistant.components.tuya.const import DPCode
from aenum import extend_enum

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass
)

from .const import LOGGER, DPCode as DPCodeExt

SENSORS_EXT: dict[str, tuple[TuyaSensorEntityDescription, ...]] = {
    # Multi-functional Sensor
    # https://developer.tuya.com/en/docs/iot/categorydgnbj?id=Kaiuz3yorvzg3
    # Air Quality Monitor
    # No specification on Tuya portal
}

def patch_tuya_entries_init(hass: HomeAssistant, data: HomeAssistantTuyaData):
    path_tuya_dpcodes()

def path_tuya_dpcodes():
    for v in DPCodeExt:
        if not v.name in DPCode._member_names_:
            extend_enum(DPCode, v.name, v.value)   
    