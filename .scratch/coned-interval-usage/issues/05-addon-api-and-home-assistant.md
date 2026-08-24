# Expose interval energy and average power to Home Assistant

Status: completed

Extend the add-on API to return the latest persisted normalized interval. Update
the existing `coned_connect` coordinator and sensor definitions to expose latest
interval energy in kWh and average interval power in W, with interval/source/
quality metadata as attributes. Do not add MQTT behavior.

## Done when

- Both entities appear through the custom integration with correct Home Assistant
  device and state classes.
- Cached readings remain readable during an upstream outage.
- Values and attributes describe the same interval.
