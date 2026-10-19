"""Log-distance V2I link budget and Shannon capacity model."""

from __future__ import annotations

import math
from dataclasses import dataclass

SPEED_OF_LIGHT_MPS = 299_792_458.0


@dataclass(frozen=True)
class RadioParameters:
    carrier_frequency_hz: float = 5.9e9
    bandwidth_hz: float = 10e6
    transmit_power_dbm: float = 20.0
    noise_psd_dbm_hz: float = -174.0
    receiver_noise_figure_db: float = 9.0
    path_loss_exponent: float = 3.25
    reference_distance_m: float = 1.0
    rsu_positions_m: tuple[float, ...] = (250.0, 500.0, 750.0)

    def __post_init__(self) -> None:
        numeric_parameters = (
            self.carrier_frequency_hz,
            self.bandwidth_hz,
            self.transmit_power_dbm,
            self.noise_psd_dbm_hz,
            self.receiver_noise_figure_db,
            self.path_loss_exponent,
            self.reference_distance_m,
            *self.rsu_positions_m,
        )
        if not all(math.isfinite(value) for value in numeric_parameters):
            raise ValueError("Radio parameters must be finite numbers.")
        if self.carrier_frequency_hz <= 0:
            raise ValueError("Carrier frequency must be positive.")
        if self.bandwidth_hz <= 0:
            raise ValueError("Channel bandwidth must be positive.")
        if self.reference_distance_m <= 0:
            raise ValueError("Reference distance must be positive.")
        if not 3.0 <= self.path_loss_exponent <= 3.5:
            raise ValueError("Path-loss exponent must be in the assigned range 3.0-3.5.")
        if not self.rsu_positions_m:
            raise ValueError("At least one RSU position is required.")

    @property
    def reference_path_loss_db(self) -> float:
        """Free-space path loss at the reference distance."""
        ratio = (
            4.0
            * math.pi
            * self.carrier_frequency_hz
            * self.reference_distance_m
            / SPEED_OF_LIGHT_MPS
        )
        return 20.0 * math.log10(ratio)

    @property
    def noise_power_dbm(self) -> float:
        """Integrated receiver noise over the configured channel bandwidth."""
        return (
            self.noise_psd_dbm_hz
            + 10.0 * math.log10(self.bandwidth_hz)
            + self.receiver_noise_figure_db
        )


def path_loss_db(distance_m: float, radio: RadioParameters) -> float:
    """Return log-distance path loss, clamping distance to the reference point."""
    if distance_m < 0:
        raise ValueError("Distance cannot be negative.")
    distance = max(distance_m, radio.reference_distance_m)
    return radio.reference_path_loss_db + (
        10.0 * radio.path_loss_exponent * math.log10(distance / radio.reference_distance_m)
    )


def nearest_rsu(position_x_m: float, radio: RadioParameters) -> float:
    """Return the nearest roadside unit's longitudinal position."""
    return min(radio.rsu_positions_m, key=lambda rsu_x: abs(position_x_m - rsu_x))


def link_budget(
    position_x_m: float,
    radio: RadioParameters,
) -> tuple[float, float, float]:
    """Return (nearest RSU position, SNR in dB, Shannon capacity in bit/s)."""
    rsu_x = nearest_rsu(position_x_m, radio)
    distance_m = abs(position_x_m - rsu_x)
    received_power_dbm = radio.transmit_power_dbm - path_loss_db(distance_m, radio)
    snr_db = received_power_dbm - radio.noise_power_dbm
    snr_linear = 10.0 ** (snr_db / 10.0)
    capacity_bps = radio.bandwidth_hz * math.log2(1.0 + snr_linear)
    return rsu_x, snr_db, capacity_bps


def packet_airtime_s(payload_bytes: int, link_capacity_bps: float) -> float:
    """Return ideal Shannon-limit airtime for one payload, excluding headers."""
    if payload_bytes <= 0:
        raise ValueError("Payload size must be positive.")
    if link_capacity_bps <= 0:
        raise ValueError("Link capacity must be positive.")
    return payload_bytes * 8.0 / link_capacity_bps
