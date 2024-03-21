"""Support for Tuya Climate."""
from __future__ import annotations

import asyncio
import functools as ft
from dataclasses import dataclass
from typing import Any, Iterable

from tuya_sharing import CustomerDevice, Manager
from tuya_iot import TuyaDevice, TuyaDeviceManager

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    RemoteEntity,
    RemoteEntityDescription,
    RemoteEntityFeature,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HomeAssistantTuyaData
from .const import DOMAIN, LOGGER, TUYA_DISCOVERY_NEW
from .ir import IR_MEDIAREMOTE_DPCODE
from .base import TuyaEntity


@dataclass
class TuyaIRRemoteEntityDescription(RemoteEntityDescription):
    """Describe an Tuya climate entity."""


IRREMOTE_DESCRIPTIONS: dict[str, TuyaIRRemoteEntityDescription] = {
    # Air Conditioner remote
    "infrared_tv": TuyaIRRemoteEntityDescription(
        key="infrared_tv",
        device_class="androidtv",
    ),
    "infrared_tvbox": TuyaIRRemoteEntityDescription(
        key="infrared_tvbox",
        device_class="tv",
    ),
    "infrared_amplifier": TuyaIRRemoteEntityDescription(
        key="infrared_amplifier",
        # device_class=MediaPlayerDeviceClass.SPEAKER,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tuya ir climate dynamically through Tuya discovery."""
    hass_data: HomeAssistantTuyaData = hass.data[DOMAIN][entry.entry_id]

    @callback
    def async_discover_device(device_ids: list[str]) -> None:
        """Discover and add a discovered Tuya climate."""
        entities: list[TuyaIRRemoteEntity] = []
        for device_id in device_ids:
            device = hass_data.device_manager.device_map[device_id]
            if device and device.category in IRREMOTE_DESCRIPTIONS:
                entities.append(
                    TuyaIRRemoteEntity(
                        device,
                        hass_data.device_manager,
                        IRREMOTE_DESCRIPTIONS[device.category],
                    )
                )
        async_add_entities(entities)

    async_discover_device([*hass_data.device_manager.device_map])

    entry.async_on_unload(
        async_dispatcher_connect(hass, TUYA_DISCOVERY_NEW, async_discover_device)
    )


class TuyaIRRemoteEntity(TuyaEntity, RemoteEntity):
    """Tuya IR remote Device."""

    def __init__(
        self,
        device: TuyaDevice,
        manager: TuyaDeviceManager,
        description: TuyaIRRemoteEntityDescription,
    ) -> None:
        """Determine which values to use."""

        self.entity_description = description
        super().__init__(device, manager)

        #LOGGER.info(f"remote init: {device.name}, {device.function}")
        self._attr_activity_list = []

        for value in self.device.function.values():
            if value and value.type == "STRING":
                self._attr_activity_list.append(value.code)

        if len(self._attr_activity_list) > 0:
            self._attr_supported_features = RemoteEntityFeature.ACTIVITY

        #LOGGER.info(f"remote init functions: {self._attr_activity_list}")
        self._attr_is_on = True

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Send commands to a device."""
        LOGGER.info(f"remote send command: {command}, kwargs {str(kwargs)}")
        num_repeats = kwargs.get(ATTR_NUM_REPEATS, 1)
        delay = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)

        for _ in range(num_repeats):
            for cmd in command:
                await self.hass.async_add_executor_job(
                    ft.partial(self._send_command, [{"code": cmd}])
                )
                await asyncio.sleep(delay)

    def turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        self._send_command([IR_MEDIAREMOTE_DPCODE.POWERON])

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        self._send_command([IR_MEDIAREMOTE_DPCODE.POWEROFF])
