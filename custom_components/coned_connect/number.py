"""Configurable values for Con Edison statistics."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ELECTRICITY_RATE, DEFAULT_ELECTRICITY_RATE, DOMAIN
from .coordinator import ConEdisonIntervalCoordinator
from .statistics import async_import_statistics


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the electricity rate control."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ElectricityRateNumber(coordinator, entry)])


class ElectricityRateNumber(CoordinatorEntity[ConEdisonIntervalCoordinator], NumberEntity):
    """Flat electricity rate used for historical cost estimates."""

    _attr_has_entity_name = True
    _attr_name = "Electricity Rate"
    _attr_icon = "mdi:currency-usd"
    _attr_native_min_value = 0
    _attr_native_max_value = 5
    _attr_native_step = 0.01
    _attr_native_unit_of_measurement = "USD/kWh"
    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator: ConEdisonIntervalCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_electricity_rate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Con Edison Interval Usage",
            manufacturer="Con Edison",
            model="Interval Usage Collector",
        )

    @property
    def native_value(self) -> float:
        """Return the configured flat rate."""
        return float(
            self.entry.options.get(CONF_ELECTRICITY_RATE, DEFAULT_ELECTRICITY_RATE)
        )

    async def async_set_native_value(self, value: float) -> None:
        """Save a new rate and recalculate historical costs."""
        self.hass.config_entries.async_update_entry(
            self.entry,
            options={**self.entry.options, CONF_ELECTRICITY_RATE: value},
        )
        async_import_statistics(self.hass, self.entry, self.coordinator.data)
        self.async_write_ha_state()
