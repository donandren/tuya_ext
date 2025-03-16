"""Support for Tuya Locks"""
from __future__ import annotations

from dataclasses import dataclass

from typing import Any

from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceNotFound
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from tuya_iot import TuyaDevice, TuyaDeviceManager, TuyaOpenAPI

from . import HomeAssistantTuyaData
from .base import TuyaEntity
from .const import DOMAIN, TUYA_DISCOVERY_NEW, TUYA_HA_SIGNAL_UPDATE_ENTITY, DPCode, DPType, LOGGER


@dataclass
class TuyaLockEntityDescription(LockEntityDescription):
    locked_dpcode: DPCode = None


LOCKS: dict[str, TuyaLockEntityDescription] = {
    # Smart-Lock
    # https://developer.tuya.com/en/docs/iot/s?id=Kb0o2xhlkxbet
    "jtmspro": TuyaLockEntityDescription(
        key=DPCode.LOCK,
        locked_dpcode=DPCode.LOCK_MOTOR_STATE,
        name=DPCode.LOCK
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up tuya lock dynamically through tuya discovery."""
    hass_data: HomeAssistantTuyaData = hass.data[DOMAIN][entry.entry_id]

    @callback
    def async_discover_device(device_ids: list[str]) -> None:
        """Discover and add a discovered tuya lock."""
        entities: list[TuyaLockEntity] = []
        for device_id in device_ids:
            device = hass_data.device_manager.device_map[device_id]
            if description := LOCKS.get(device.category):
                entities.append(
                    TuyaLockEntity(device, hass_data.device_manager, description)
                )

        async_add_entities(entities)

    async_discover_device([*hass_data.device_manager.device_map])

    entry.async_on_unload(
        async_dispatcher_connect(hass, TUYA_DISCOVERY_NEW, async_discover_device)
    )

def get_lock_temporary_key(api:TuyaOpenAPI, device_id: str) -> list | None:
    response = api.post(f"/v1.0/smart-lock/devices/{device_id}/password-ticket")
    LOGGER.info(f"get_lock_temporary_key result: {response}")
    if response["success"]:
        return response["result"]
    return None

def send_lock_open_command(api:TuyaOpenAPI, device_id: str, ticket_id: str, open: bool) -> list | None:
    command = {"device_id": device_id, "ticket_id": ticket_id, "open": open}
    response = api.post(
        f"/v1.0/smart-lock/devices/{device_id}/password-free/door-operate", command
    )
    LOGGER.info(f"send_lock_open_command result: {response}")

    return response


class TuyaLockEntity(TuyaEntity, LockEntity):
    _locked_dpcode: DPCode | None = None
    entity_description: TuyaLockEntityDescription | None = None

    def __init__(
            self,
            device: TuyaDevice,
            device_manager: TuyaDeviceManager,
            description: TuyaLockEntityDescription
    ) -> None:
        super().__init__(device, device_manager)

        self.entity_description = description
        # just in case let' do periodic poll so when we wait for update
        # and update is not received we force pull it
        self._attr_should_poll = True

        if code := self.find_dpcode((DPCode.LOCK_MOTOR_STATE,), dptype=DPType.BOOLEAN):
            self._locked_dpcode = code
        self.force_update_max = 10
        self.force_update_device_state = self.force_update_max

    async def async_added_to_hass(self) -> None:
        """Call when entity is added to hass."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{TUYA_HA_SIGNAL_UPDATE_ENTITY}_{self.device.id}",
                self.device_status_updated,
            )
        )

    def device_status_updated(self) -> None:
        # todo: clean up
        autolock = self.device.status["automatic_lock"]
        LOGGER.info(
            f"update: locked={self.is_locked} autolock={autolock} locking:{self._attr_is_locking} unlocking: {self._attr_is_unlocking} {self.device.status}"
        )
        if self._attr_is_locking is True:
            if self.is_locked:
                self._attr_is_locking = None
        if self._attr_is_unlocking is True:
            if not self.is_locked:
                self._attr_is_unlocking = None
        self.schedule_update_ha_state()

    def _send_lock(self, lock: bool) -> None:
        key = get_lock_temporary_key(self.device_manager.api, self.device.id)
        if key:
            res = send_lock_open_command(self.device_manager.api, self.device.id, key["ticket_id"], not lock)
            if res["success"] == True and res["result"] == True:
                LOGGER.debug(f"successfully sent locked/unlocked")
                if lock:
                    self._attr_is_locking = True
                else:
                    self._attr_is_unlocking = True
            else:
                code = res["code"]
                msg = res["msg"]
                raise RuntimeError(
                    f"Failed to lock or unlock the door!\ncode: {code}\n{msg}"
                )
        else:
            raise RuntimeError(f"Failed to lock or unlock the door!")

    @property
    def is_locked(self) -> bool | None:
        """Return true if the lock is locked."""
        if self._locked_dpcode is None:
            return None

        status = self.device.status.get(self._locked_dpcode)

        if status is None:
            return None

        return not status

    def lock(self, **kwargs: Any) -> None:
        self._send_lock(True)

    def unlock(self, **kwargs: Any) -> None:
        self._send_lock(False)

    def get_device_status(self) -> list:
        response = self.device_manager.api.get(f"/v1.0/devices/{self.device.id}/status")
        if response["success"]:
            return response["result"]
        return []

    def update(self):
        self.force_update_device_state = self.force_update_device_state - 1
        LOGGER.debug(f"lock.update status current: self.force_update_device_state:{self.force_update_device_state}\n{self.device.status}")

        if self.force_update_device_state < 1 or self.is_locking or self.is_unlocking:
            self.force_update_device_state = self.force_update_max
            # force update state
            status = self.get_device_status()
            LOGGER.info(f"lock force update status current:{self.device.status} new: {status}")
            # emulate standard push update from tuya iot, as lock might miss updates ?
            # self.device_manager._on_device_report(self.device.id, status) 
