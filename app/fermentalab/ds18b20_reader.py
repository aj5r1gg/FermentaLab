"""DS18B20 temperature acquisition adapter.

Read-only sensor interface. No GPIO switching, actuator control,
or authority to enable heating or cooling.

Measurements from this adapter are not authoritative until passed
through FermentaLab's established validation and calibration path.
"""

from math import isfinite


class SensorReadError(RuntimeError):
    """Sensor acquisition failed or returned an invalid measurement."""


class DS18B20Reader:
    def __init__(self, *, sensor_id: str, sensor):
        if not isinstance(sensor_id, str) or not sensor_id:
            raise ValueError("sensor_id must be a nonempty string")
        if not callable(getattr(sensor, "get_temperature", None)):
            raise TypeError("sensor must support get_temperature()")

        self.sensor_id = sensor_id
        self._sensor = sensor

    def read_celsius(self) -> float:
        try:
            value = self._sensor.get_temperature()
        except Exception as exc:
            raise SensorReadError(
                f"DS18B20 acquisition failed: {self.sensor_id}"
            ) from exc

        if type(value) not in (int, float):
            raise SensorReadError("DS18B20 returned a nonnumeric value")

        temperature = float(value)

        if not isfinite(temperature):
            raise SensorReadError("DS18B20 returned a nonfinite value")

        if not -55.0 <= temperature <= 125.0:
            raise SensorReadError(
                "DS18B20 reading outside sensor operating range"
            )

        return temperature


def open_ds18b20(*, hardware_id: str) -> DS18B20Reader:
    """Find one specifically identified physical DS18B20.

    The optional W1ThermSensor dependency is imported only when
    physical hardware acquisition is explicitly requested.
    """
    if not isinstance(hardware_id, str) or not hardware_id:
        raise ValueError("hardware_id must be a nonempty string")

    try:
        from w1thermsensor import W1ThermSensor
    except ImportError as exc:
        raise SensorReadError(
            "Install w1thermsensor on the Raspberry Pi"
        ) from exc

    try:
        matching = [
            sensor
            for sensor in W1ThermSensor.get_available_sensors()
            if sensor.id == hardware_id
            and sensor.type_name == "DS18B20"
        ]
    except Exception as exc:
        raise SensorReadError("DS18B20 discovery failed") from exc

    if len(matching) != 1:
        raise SensorReadError(
            "Expected exactly one matching DS18B20 sensor"
        )

    return DS18B20Reader(
        sensor_id=hardware_id,
        sensor=matching[0],
    )


class DS18B20ChamberSensor:
    """Adapt DS18B20 acquisition to FermentaLab's chamber reading.

    This class supplies measurements, not control authority.
    It does not establish calibration or sensor qualification.
    """

    def __init__(self, *, reader: DS18B20Reader, clock=None):
        from time import monotonic

        if not isinstance(reader, DS18B20Reader):
            raise TypeError("reader must be DS18B20Reader")

        if clock is None:
            clock = monotonic

        if not callable(clock):
            raise TypeError("clock must be callable")

        self._reader = reader
        self._clock = clock
        self._last_timestamp = None

    @property
    def sensor_id(self) -> str:
        return self._reader.sensor_id

    def read(self):
        from fermentalab.sensors import ChamberTemperatureReading

        # Acquire the measurement first. Timestamp it afterwards.
        # A failed acquisition must never produce a valid reading.
        temperature = self._reader.read_celsius()

        try:
            timestamp = self._clock()
        except Exception as exc:
            raise SensorReadError(
                "DS18B20 measurement timestamp unavailable"
            ) from exc

        if (
            type(timestamp) not in (int, float)
            or not isfinite(timestamp)
            or timestamp < 0
        ):
            raise SensorReadError(
                "DS18B20 measurement timestamp invalid"
            )

        if (
            self._last_timestamp is not None
            and timestamp <= self._last_timestamp
        ):
            raise SensorReadError(
                "DS18B20 measurement timestamp did not advance"
            )

        reading = ChamberTemperatureReading(
            sensor_id=self.sensor_id,
            temperature_c=temperature,
            measured_at_s=float(timestamp),
        )

        self._last_timestamp = float(timestamp)
        return reading
