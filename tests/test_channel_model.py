import math
import unittest

from src.channel_model import (
    RadioParameters,
    link_budget,
    packet_airtime_s,
    path_loss_db,
)
from src.run_experiments import (
    PacketAttempt,
    VehicleTrace,
    _aggregate_repeats,
    _channel_busy_time_s,
    _collided_packets,
    _position_at,
    run_scenario,
)


class ChannelModelTests(unittest.TestCase):
    def setUp(self):
        self.radio = RadioParameters()

    def test_reference_loss_is_free_space_loss_at_one_metre(self):
        self.assertAlmostEqual(path_loss_db(1.0, self.radio), 47.87, delta=0.02)

    def test_path_loss_does_not_fall_below_reference_loss(self):
        self.assertEqual(
            path_loss_db(0.0, self.radio),
            self.radio.reference_path_loss_db,
        )

    def test_noise_floor_includes_bandwidth_and_receiver_noise_figure(self):
        self.assertAlmostEqual(self.radio.noise_power_dbm, -95.0)

    def test_shannon_capacity_at_zero_db_snr_equals_bandwidth(self):
        noise_power_dbm = -100.0
        base_radio = RadioParameters(
            bandwidth_hz=10e6,
            noise_psd_dbm_hz=-170.0,
            receiver_noise_figure_db=0.0,
            rsu_positions_m=(1.0,),
        )
        custom_radio = RadioParameters(
            bandwidth_hz=10e6,
            transmit_power_dbm=noise_power_dbm + base_radio.reference_path_loss_db,
            noise_psd_dbm_hz=-170.0,
            receiver_noise_figure_db=0.0,
            rsu_positions_m=(1.0,),
        )
        _, snr_db, capacity_bps = link_budget(1.0, custom_radio)
        self.assertAlmostEqual(snr_db, 0.0, places=10)
        self.assertAlmostEqual(capacity_bps, 10e6, delta=1e-6)

    def test_packet_airtime_uses_payload_bits_over_shannon_rate(self):
        self.assertAlmostEqual(packet_airtime_s(32, 8e6), 32e-6)

    def test_rejects_path_loss_exponent_outside_assignment_range(self):
        with self.assertRaises(ValueError):
            RadioParameters(path_loss_exponent=2.9)


class SharedChannelTests(unittest.TestCase):
    def test_position_is_interpolated_between_sumo_samples(self):
        trace = VehicleTrace([0.05, 0.10], [10.0, 20.0])
        self.assertEqual(_position_at(trace, 0.075), 15.0)
        self.assertEqual(_position_at(trace, 0.0), 10.0)

    def test_overlapping_packets_are_both_marked_as_collisions(self):
        attempts = [
            PacketAttempt(0.0, 0.001, 250.0, 10.0),
            PacketAttempt(0.0005, 0.0015, 500.0, 10.0),
            PacketAttempt(0.002, 0.003, 750.0, 10.0),
        ]
        self.assertEqual(_collided_packets(attempts), {0, 1})

    def test_busy_time_counts_overlapping_airtime_once(self):
        attempts = [
            PacketAttempt(0.0, 0.001, 250.0, 10.0),
            PacketAttempt(0.0005, 0.0015, 500.0, 10.0),
            PacketAttempt(0.002, 0.003, 750.0, 10.0),
        ]
        self.assertTrue(math.isclose(_channel_busy_time_s(attempts), 0.0025))

    def test_non_overlapping_packets_are_not_collisions(self):
        attempts = [
            PacketAttempt(0.0, 0.001, 250.0, 10.0),
            PacketAttempt(0.001, 0.002, 500.0, 10.0),
        ]
        self.assertEqual(_collided_packets(attempts), set())

    def test_single_vehicle_scenario_is_reproducible_and_collision_free(self):
        trace = VehicleTrace([0.05, 1.0], [250.0, 250.0])
        first = run_scenario(1, {"veh0": trace}, 1.0, 100, RadioParameters(), 42)
        second = run_scenario(1, {"veh0": trace}, 1.0, 100, RadioParameters(), 42)
        self.assertEqual(first, second)
        self.assertEqual(first["generated_packets"], 10)
        self.assertEqual(first["collided_packets"], 0)
        self.assertEqual(first["packet_delivery_ratio_percent"], 100.0)

    def test_repeat_aggregation_uses_pooled_packet_delivery_ratio(self):
        run = {
            "vehicle_count": 1,
            "upload_interval_ms": 50,
            "updates_per_vehicle_per_s": 20.0,
            "payload_bytes": 32,
            "generated_packets": 10,
            "collided_packets": 2,
            "successful_packets": 8,
            "packet_delivery_ratio_percent": 80.0,
            "offered_load_mbps": 0.1,
            "effective_shannon_capacity_mbps": 10.0,
            "channel_utilisation_percent": 1.0,
            "channel_busy_time_percent": 1.0,
            "residual_bandwidth_mhz": 9.9,
            "residual_capacity_mbps": 9.9,
            "mean_snr_db": 10.0,
            "minimum_snr_db": 5.0,
            "rsu_250m_packets": 10,
            "rsu_500m_packets": 0,
            "rsu_750m_packets": 0,
            "saturated_over_60_percent": False,
        }
        aggregated = _aggregate_repeats([run, run])
        self.assertEqual(aggregated["generated_packets"], 20)
        self.assertEqual(aggregated["collided_packets"], 4)
        self.assertEqual(aggregated["packet_delivery_ratio_percent"], 80.0)
        self.assertEqual(aggregated["repeats"], 2)


if __name__ == "__main__":
    unittest.main()
