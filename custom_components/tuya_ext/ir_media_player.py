"""Support for Tuya Climate."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tuya_iot import TuyaDevice, TuyaDeviceManager

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityDescription,
    MediaPlayerEntityFeature,
    MediaPlayerDeviceClass,
    MediaType
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HomeAssistantTuyaData, TuyaDeviceListener
from .base import IntegerTypeData, TuyaEntity
from .const import DOMAIN, TUYA_DISCOVERY_NEW, DPCode, DPType, LOGGER
from .ir import IR_MEDIAREMOTE_DPCODE as IR_DP_CODE

@dataclass
class TuyaIRRemoteEntityDescription(MediaPlayerEntityDescription):
    """Describe an Tuya climate entity."""

IRREMOTE_DESCRIPTIONS: dict[str, TuyaIRRemoteEntityDescription] = {
    # Air Conditioner remote
    "infrared_tv": TuyaIRRemoteEntityDescription(
        key="infrared_tv",
        device_class="androidtv",
    ),
    "infrared_tvbox": TuyaIRRemoteEntityDescription(
        key="infrared_tvbox",
        device_class=MediaPlayerDeviceClass.TV,
    ),
    "infrared_amplifier": TuyaIRRemoteEntityDescription(
        key="infrared_amplifier",
        device_class=MediaPlayerDeviceClass.SPEAKER,
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
        entities: list[TuyaIRClimateEntity] = []
        for device_id in device_ids:
            device = hass_data.device_manager.device_map[device_id]
            if device and device.category in IRREMOTE_DESCRIPTIONS:
                entities.append(
                    TuyaIRRemoteEntity(
                        device,
                        hass_data.device_manager,
                        IRREMOTE_DESCRIPTIONS[device.category]
                    )
                )
        async_add_entities(entities)

    async_discover_device([*hass_data.device_manager.device_map])

    entry.async_on_unload(
        async_dispatcher_connect(hass, TUYA_DISCOVERY_NEW, async_discover_device)
    )

class TuyaIRRemoteEntity(TuyaEntity, MediaPlayerEntity):
    """Tuya IR remote Device."""

    def __init__(
        self,
        device: TuyaDevice,
        device_manager: TuyaDeviceManager,
        description: TuyaIRRemoteEntityDescription
    ) -> None:
        """Determine which values to use."""

        self.entity_description = description

        super().__init__(device, device_manager)

        self._attr_app_id = "tv1"
        self._attr_app_name = "tv,name"
        self._attr_available = True

        #make device use poll instead wait for update
        #as standard tuya notification system does not work ir remotes?
        #self._attr_should_poll = True
        #self._attr_force_update = True
        self._attr_assumed_state = True
        self._attr_supported_features = (
            #MediaPlayerEntityFeature.PAUSE
            #| MediaPlayerEntityFeature.VOLUME_STEP
            MediaPlayerEntityFeature.VOLUME_MUTE
            #| MediaPlayerEntityFeature.NEXT_TRACK
            | MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
            #| MediaPlayerEntityFeature.PLAY
            #| MediaPlayerEntityFeature.STOP
            #| MediaPlayerEntityFeature.PLAY_MEDIA
        )
        self._attr_available = device.online
        self._attr_is_on = True
        self._attr_media_content_type  =MediaType.MUSIC

    def volume_up(self) -> None:
        """implement volume up"""
        self._send_command([{"code":IR_DP_CODE.VOLUMEUP}])

    def volume_down(self) -> None:
        """implement volume down"""
        self._send_command([{"code":IR_DP_CODE.VOLUMEDOWN}])
    
    def mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        raise NotImplementedError()
    
    def turn_off(self) -> None:
        """Turn the media player off."""
        raise NotImplementedError()
    
    def turn_on(self) -> None:
        """Turn the media player on."""
        raise NotImplementedError()

    async def async_media_play(self) -> None:
        """Send play command."""
        raise NotImplementedError()

    async def async_media_pause(self) -> None:
        """Send pause command."""
        raise NotImplementedError()

    async def async_media_play_pause(self) -> None:
        """Send play/pause command."""
        raise NotImplementedError()

    async def async_media_stop(self) -> None:
        """Send stop command."""
        raise NotImplementedError()
    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        raise NotImplementedError()
    async def async_media_next_track(self) -> None:
        """Send next track command."""
        raise NotImplementedError()

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        raise NotImplementedError()
    
    # @property
    # def is_volume_muted(self) -> bool | None:
    #     """Boolean if volume is currently muted."""
    #     return self._attr_is_volume_muted
