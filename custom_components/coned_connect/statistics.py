"""Import collector history through Home Assistant's external statistics API."""

from __future__ import annotations

from typing import Any

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant

from .const import CONF_ELECTRICITY_RATE, DEFAULT_ELECTRICITY_RATE, DOMAIN
from .history import hourly_usage


def async_import_statistics(
    hass: HomeAssistant, entry: ConfigEntry, data: dict[str, Any]
) -> None:
    """Import complete hourly buckets, replacing corrected rows idempotently."""
    rows = data.get("_interval_history")
    if not isinstance(rows, list):
        return
    usage = hourly_usage(rows)
    if not usage:
        return

    statistic_prefix = f"{DOMAIN}:{entry.entry_id.lower()}"
    energy_metadata: StatisticMetaData = {
        "has_sum": True,
        "mean_type": StatisticMeanType.NONE,
        "name": "Con Edison Hourly Energy",
        "source": DOMAIN,
        "statistic_id": f"{statistic_prefix}_energy",
        "unit_class": "energy",
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
    }
    energy_statistics: list[StatisticData] = [
        {
            "start": item.start,
            "state": item.cumulative_energy_kwh,
            "sum": item.cumulative_energy_kwh,
        }
        for item in usage
    ]
    async_add_external_statistics(hass, energy_metadata, energy_statistics)

    rate = float(entry.options.get(CONF_ELECTRICITY_RATE, DEFAULT_ELECTRICITY_RATE))
    currency = hass.config.currency
    cost_metadata: StatisticMetaData = {
        "has_sum": True,
        "mean_type": StatisticMeanType.NONE,
        "name": "Con Edison Estimated Cost",
        "source": DOMAIN,
        "statistic_id": f"{statistic_prefix}_cost",
        "unit_class": None,
        "unit_of_measurement": currency,
    }
    cost_statistics: list[StatisticData] = [
        {
            "start": item.start,
            "state": item.cumulative_energy_kwh * rate,
            "sum": item.cumulative_energy_kwh * rate,
        }
        for item in usage
    ]
    async_add_external_statistics(hass, cost_metadata, cost_statistics)

    power_metadata: StatisticMetaData = {
        "has_sum": False,
        "mean_type": StatisticMeanType.ARITHMETIC,
        "name": "Con Edison Hourly Average Power",
        "source": DOMAIN,
        "statistic_id": f"{statistic_prefix}_power",
        "unit_class": "power",
        "unit_of_measurement": UnitOfPower.WATT,
    }
    power_statistics: list[StatisticData] = [
        {
            "start": item.start,
            "mean": item.average_power_w,
        }
        for item in usage
    ]
    async_add_external_statistics(hass, power_metadata, power_statistics)
