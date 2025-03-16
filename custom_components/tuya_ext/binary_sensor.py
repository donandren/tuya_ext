"""Support for Tuya binary sensors."""
from __future__ import annotations

from dataclasses import dataclass

from tuya_iot import TuyaDevice, TuyaDeviceManager

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HomeAssistantTuyaData
from .base import TuyaEntity
from .const import DOMAIN, TUYA_DISCOVERY_NEW, DPCode, TUYA_HA_SIGNAL_UPDATE_ENTITY, LOGGER

@dataclass
class TuyaBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Tuya binary sensor."""

    # DPCode, to use. If None, the key will be used as DPCode
    dpcode: DPCode | None = None

    # Value or values to consider binary sensor to be "on"
    on_value: bool | float | int | str | set[bool | float | int | str] = True


# Commonly used sensors
TAMPER_BINARY_SENSOR = TuyaBinarySensorEntityDescription(
    key=DPCode.TEMPER_ALARM,
    name="Tamper",
    device_class=BinarySensorDeviceClass.TAMPER,
    entity_category=EntityCategory.DIAGNOSTIC,
)

DOOR_BELL_SENSORS: dict[str, tuple[TuyaBinarySensorEntityDescription, ...]] = {
    # Kinetic key Doorbell
    "wxml": (
        TuyaBinarySensorEntityDescription(
            key=DPCode.DOORBELL_CALL,
            name="Doorbell",
            device_class=BinarySensorDeviceClass.SOUND,
            on_value=1,
        ),
    ),
}



# All descriptions can be found here. Mostly the Boolean data types in the
# default status set of each category (that don't have a set instruction)
# end up being a binary sensor.
# https://developer.tuya.com/en/docs/iot/standarddescription?id=K9i5ql6waswzq
BINARY_SENSORS: dict[str, tuple[TuyaBinarySensorEntityDescription, ...]] = {
    # Smart-Lock
    # https://developer.tuya.com/en/docs/iot/s?id=Kb0o2xhlkxbet
    "jtmspro": (
        TuyaBinarySensorEntityDescription(
            key=DPCode.CLOSED_OPENED,
            device_class=BinarySensorDeviceClass.DOOR,
            on_value={"open", "opened"},
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tuya binary sensor dynamically through Tuya discovery."""
    hass_data: HomeAssistantTuyaData = hass.data[DOMAIN][entry.entry_id]

    @callback
    def async_discover_device(device_ids: list[str]) -> None:
        """Discover and add a discovered Tuya binary sensor."""
        entities: list[TuyaBinarySensorEntity] = []
        for device_id in device_ids:
            device = hass_data.device_manager.device_map[device_id]
            if descriptions := BINARY_SENSORS.get(device.category):
                for description in descriptions:
                    dpcode = description.dpcode or description.key
                    if dpcode in device.status:
                        entities.append(
                            TuyaBinarySensorEntity(
                                device, hass_data.device_manager, description
                            )
                        )
            if descriptions := DOOR_BELL_SENSORS.get(device.category):
                for description in descriptions:
                    dpcode = description.dpcode or description.key
                    if dpcode in device.status:
                        entities.append(
                            DoorbellSensorEntity(
                                device, hass_data.device_manager, description
                            )
                        )

        async_add_entities(entities)

    async_discover_device([*hass_data.device_manager.device_map])

    entry.async_on_unload(
        async_dispatcher_connect(hass, TUYA_DISCOVERY_NEW, async_discover_device)
    )

class TuyaBinarySensorEntity(TuyaEntity, BinarySensorEntity):
    """Tuya Binary Sensor Entity."""

    entity_description: TuyaBinarySensorEntityDescription

    def __init__(
        self,
        device: TuyaDevice,
        device_manager: TuyaDeviceManager,
        description: TuyaBinarySensorEntityDescription,
    ) -> None:
        """Init Tuya binary sensor."""
        super().__init__(device, device_manager)
        self.entity_description = description
        self._attr_unique_id = f"{super().unique_id}{description.key}"

    @property
    def is_on(self) -> bool:
        """Return true if sensor is on."""
        dpcode = self.entity_description.dpcode or self.entity_description.key
        if dpcode not in self.device.status:
            return False

        if isinstance(self.entity_description.on_value, set):
            return self.device.status[dpcode] in self.entity_description.on_value

        return self.device.status[dpcode] == self.entity_description.on_value

class DoorbellSensorEntity(TuyaBinarySensorEntity):
    def __init__(
        self,
        device: TuyaDevice,
        device_manager: TuyaDeviceManager,
        description: TuyaBinarySensorEntityDescription,
    ) -> None:
        """Init Tuya binary sensor."""
        super().__init__(device, device_manager, description)
        # device status notify only ring the bell, but not when stopped so we
        # use the internal ha poll mecahnism to make it off after some time
        self._attr_should_poll = True
        self.set_status_off()
    
    def set_status_off(self):
        """ this bell doesn't report off state at all so we manually set it"""
        dpcode = self.entity_description.dpcode or self.entity_description.key

        status = [{"code":dpcode, "value": 0}]
        # emulate standard push update from tuya iot, as door doesn notify when ring has stopped ?
        self.device_manager._on_device_report(self.device.id, status) 
        self.turn_off_next = 0

    async def async_update(self):
        # LOGGER.info(f"Doorbell.async_update() {self.device.status}")
        if self.is_on and self.turn_off_next > 0:
            self.turn_off_next = self.turn_off_next - 1
            if self.turn_off_next < 1:
                self.set_status_off()

    def async_update_and_write_state(self):
        # LOGGER.info(f"Doorbell.async_write_ha_state() {self.device.status}")
        if self.is_on:
            self.turn_off_next = 2 # after 31-60 seconds ring will stop
        self.schedule_update_ha_state()

