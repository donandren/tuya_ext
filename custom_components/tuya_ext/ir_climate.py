"""Support for Tuya Climate."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tuya_iot import TuyaDevice, TuyaDeviceManager

from homeassistant.components.climate import (
    SWING_BOTH,
    SWING_HORIZONTAL,
    SWING_OFF,
    SWING_ON,
    SWING_VERTICAL,
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HomeAssistantTuyaData, TuyaDeviceListener
from .base import IntegerTypeData, TuyaEntity
from .const import DOMAIN, TUYA_DISCOVERY_NEW, DPCode, DPType, LOGGER
from .ir import TUYA_HVAC_IR_CLIMATE_CODE_TO_HA, IR_DPCODE, TUYA_HVAC_IR_CLIMATE_FAN_CODE_TO_NAME

@dataclass
class TuyaIRClimateEntityDescription(ClimateEntityDescription):
    """Describe an Tuya ir climate entity."""


CLIMATE_DESCRIPTIONS: dict[str, TuyaIRClimateEntityDescription] = {
    # Air Conditioner remote
    "infrared_ac": TuyaIRClimateEntityDescription(
        key="infrared_ac", force_update=True, icon="mdi:air-conditioner"
    )
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
            if device and device.category in CLIMATE_DESCRIPTIONS:
                entities.append(
                    TuyaIRClimateEntity(
                        device,
                        hass_data.device_manager,
                        CLIMATE_DESCRIPTIONS[device.category]
                    )
                )
        async_add_entities(entities)

    async_discover_device([*hass_data.device_manager.device_map])

    entry.async_on_unload(
        async_dispatcher_connect(hass, TUYA_DISCOVERY_NEW, async_discover_device)
    )


class TuyaIRClimateEntity(TuyaEntity, ClimateEntity):
    """Tuya IR Climate Device."""

    _temperature: IntegerTypeData | None = None
    _hvac_to_tuya: dict[str, str]
    _fan_to_tuya: dict[str, int]
    _set_temperature: IntegerTypeData | None = None
    entity_description: TuyaIRClimateEntityDescription
    _attr_name = None
    _command_power_on = {"code": IR_DPCODE.POWERON}
    _command_power_off = {"code": IR_DPCODE.POWEROFF}

    def __init__(
        self,
        device: TuyaDevice,
        device_manager: TuyaDeviceManager,
        description: TuyaIRClimateEntityDescription
    ) -> None:
        """Determine which values to use."""

        self.entity_description = description

        super().__init__(device, device_manager)

        # make device use poll instead wait for update
        # as standard tuya notification system does not work ir remotes?
        self._attr_should_poll = True
        self._attr_force_update = True

        # Default to Celsius
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS

        # Figure out current temperature, use preferred unit or what is available
        celsius_type = self.find_dpcode_integer_data(
            (DPCode.TEMP, IR_DPCODE.TEMP), dptype=DPType.ENUM
        )

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._current_temperature = celsius_type

        # Figure out setting temperature, use preferred unit or what is available
        celsius_type = self.find_dpcode_integer_data(
            (IR_DPCODE.TEMP, DPCode.TEMP), dptype=DPType.ENUM, prefer_function=True
        )

        self._set_temperature = celsius_type
        self._attr_target_temperature_step = 1
        self._attr_supported_features |= ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON

        # Get integer type data for the dpcode to set temperature, use
        # it to define min, max & step temperatures
        if self._set_temperature:
            self._attr_supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
            self._attr_max_temp = self._set_temperature.max_scaled
            self._attr_min_temp = self._set_temperature.min_scaled
            self._attr_target_temperature_step = self._set_temperature.step_scaled

        # Determine HVAC modes
        self._attr_hvac_modes: list[HVACMode] = []
        self._hvac_to_tuya = {}
        if mode_values := self.find_dpcode_integer_data(
            DPCode.MODE, dptype=DPType.ENUM, prefer_function=True
        ):
            self._attr_hvac_modes = [HVACMode.OFF]
            unknown_hvac_modes: list[str] = []
            for tuya_mode in range(mode_values.min, mode_values.max + 1):
                if tuya_mode in TUYA_HVAC_IR_CLIMATE_CODE_TO_HA:
                    ha_mode = TUYA_HVAC_IR_CLIMATE_CODE_TO_HA[tuya_mode]
                    self._hvac_to_tuya[ha_mode] = tuya_mode
                    self._attr_hvac_modes.append(ha_mode)
                else:
                    unknown_hvac_modes.append(tuya_mode)
            if unknown_hvac_modes:  # Tuya modes are presets instead of hvac_modes
                self._attr_hvac_modes.append(description.switch_only_hvac_mode)
                self._attr_preset_modes = unknown_hvac_modes
                self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE

        # Determine fan modes
        if int_type := self.find_dpcode_integer_data(
            (IR_DPCODE.WIND, DPCode.WIND),
            dptype=DPType.ENUM,
            prefer_function=True,
        ):
            self._attr_supported_features |= ClimateEntityFeature.FAN_MODE
            self._attr_fan_modes = []
            self._fan_to_tuya = {}
            for mode in range(int_type.min, int_type.max + 1):
                name = f"fan mode #{mode}"
                if mode in TUYA_HVAC_IR_CLIMATE_FAN_CODE_TO_NAME:
                    name = TUYA_HVAC_IR_CLIMATE_FAN_CODE_TO_NAME[mode]
                self._fan_to_tuya[name] = mode
                self._attr_fan_modes.append(name)

    def get_device_status(self) -> list:
        response = self.device_manager.api.get(f"/v1.0/devices/{self.device.id}/status")
        if response["success"]:
            return response["result"]
        return []

    def update(self):
        """Retrieve latest state."""
        status = self.get_device_status()
        # emulate standard push update from tuya iot, as ir climate doesn notify updates ?
        self.device_manager._on_device_report(self.device.id, status) 

    def set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        current_on = self.hvac_mode == HVACMode.OFF
        next_on = hvac_mode == HVACMode.OFF
        LOGGER.info(
            f"set_hvac_mode hvac_mode:{hvac_mode} next_on:{next_on}, current:{current_on}"
        )

        commands = []
        if current_on != next_on:
            commands.append(
                self._command_power_off if next_on else self._command_power_on
            )
            self._send_command(commands)
            commands = []
        if hvac_mode in self._hvac_to_tuya:
            commands.append(
                {"code": IR_DPCODE.MODE, "value": self._hvac_to_tuya[hvac_mode]}
            )
            self._send_command(commands)

        self.update()

    def set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        self.set_hvac_mode(preset_mode)

    def set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        if fan_mode:
            if fan_mode in self._fan_to_tuya:
                self._send_command(
                    [{"code": IR_DPCODE.WIND, "value": self._fan_to_tuya[fan_mode]}]
                )
            else:
                raise RuntimeError(f"Can not set fan mode - invalid value: {fan_mode}")
            self.update()

    def set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if self._set_temperature is None:
            raise RuntimeError(
                "Cannot set target temperature, device doesn't provide methods to"
                " set it"
            )
        if self.hvac_mode == HVACMode.OFF:
            self.turn_on()

        temp = round(self._set_temperature.scale_value_back(kwargs["temperature"]))
        self._send_command([{"code": self._set_temperature.dpcode, "value": temp}])
        self.update()

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature currently set to be reached."""
        if self._current_temperature is None:
            return None

        temperature = self.device.status.get(self._current_temperature.dpcode)
        if temperature is None:
            return None

        return self._current_temperature.scale_value(int(temperature))

    @property
    def hvac_mode(self) -> HVACMode:
        """Return hvac mode."""
        power = self.device.status.get(DPCode.POWER)
        mode = self.device.status.get(DPCode.MODE)

        if power is not None and mode is not None:
            power = int(power)
            mode = int(mode)
            if power == 0:
                return HVACMode.OFF
            elif mode in TUYA_HVAC_IR_CLIMATE_CODE_TO_HA:
                return TUYA_HVAC_IR_CLIMATE_CODE_TO_HA[mode]
            else:
                return HVACMode.HEAT_COOL

        return HVACMode.OFF

    @property
    def preset_mode(self) -> str | None:
        """Return preset mode."""
        return str(self.hvac_mode)

    @property
    def fan_mode(self) -> str | None:
        """Return fan mode."""
        wind = self.device.status.get(DPCode.WIND)
        if wind is None:
            return None

        return TUYA_HVAC_IR_CLIMATE_FAN_CODE_TO_NAME[int(wind)]

    def turn_on(self) -> None:
        """Turn the device on, retaining current HVAC (if supported)."""
        self._send_command([self._command_power_on])

    def turn_off(self) -> None:
        """Turn the device on, retaining current HVAC (if supported)."""
        self._send_command([self._command_power_off])

    def find_dpcode_integer_data(
        self,
        dpcodes: str | DPCode | tuple[DPCode, ...] | None,
        *,
        prefer_function: bool = False,
        dptype: DPType | None = None,
    ) -> DPCode | IntegerTypeData | None:
        """Find a matching DP code available on for this device."""
        if dpcodes is None:
            return None

        if isinstance(dpcodes, str):
            dpcodes = (DPCode(dpcodes),)
        elif not isinstance(dpcodes, tuple):
            dpcodes = (dpcodes,)

        order = ["status_range", "function"]
        if prefer_function:
            order = ["function", "status_range"]

        # When we are not looking for a specific datatype, we can append status for
        # searching
        if not dptype:
            order.append("status")

        for dpcode in dpcodes:
            for key in order:
                if dpcode not in getattr(self.device, key):
                    continue

                if (dptype == DPType.INTEGER or dptype == DPType.ENUM) and (
                    getattr(self.device, key)[dpcode].type == DPType.INTEGER
                    or getattr(self.device, key)[dpcode].type.casefold()
                    == DPType.ENUM.casefold()
                ):
                    if not (
                        integer_type := IntegerTypeData.from_json(
                            dpcode, getattr(self.device, key)[dpcode].values
                        )
                    ):
                        continue
                    return integer_type

                if dptype not in (DPType.ENUM, DPType.INTEGER):
                    return dpcode

        return None
