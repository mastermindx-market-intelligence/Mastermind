"""Fail-closed readiness contract between installed producer and fleet validator."""
import unittest
from unittest.mock import patch
import studio_direct_control as control


class InstalledFleetReadiness(unittest.TestCase):
    def status(self, **overrides):
        gateway = {'account': 'chatgpt1', 'loaded': True, 'running': True}
        tunnel = {'account': 'chatgpt1', 'loaded': True, 'running': True,
                  'healthy': True, 'ready': True, 'configurationDrift': False,
                  'tunnelReady': True, 'gatewayReady': True,
                  'controlPlanePollReady': True, 'managedAliasRunning': False}
        tunnel.update(overrides)
        with patch.object(control, '_invoke_from', side_effect=[gateway, tunnel]) as owner:
            v = control.installed_status('chatgpt1')
        self.assertEqual(owner.call_count, 2)
        self.assertTrue(all(call.args[0] == control.INSTALLED_CONTROL_ROOT for call in owner.call_args_list))
        self.assertTrue(all(call.args[2] == 'status' for call in owner.call_args_list))
        return v

    def test_healthy_ready(self):
        self.assertTrue(self.status()['ready'])

    def test_false_readiness_when_control_poll_not_ready(self):
        self.assertFalse(self.status(controlPlanePollReady=False)['ready'])

    def test_false_readiness_on_degraded_custody_or_health(self):
        for flag in ('loaded', 'running', 'healthy', 'ready', 'tunnelReady', 'gatewayReady'):
            with self.subTest(flag=flag):
                self.assertFalse(self.status(**{flag: False})['ready'])
        self.assertFalse(self.status(configurationDrift=True)['ready'])
        self.assertFalse(self.status(managedAliasRunning=True)['ready'])

    def test_missing_status_flag_not_optimistically_ready(self):
        row = self.status()
        row['tunnel'].pop('controlPlanePollReady')
        gateway = row['gateway']
        with patch.object(control, '_invoke_from', side_effect=[gateway, row['tunnel']]):
            self.assertFalse(control.installed_status('chatgpt1')['ready'])

    def test_partial_degraded_seat_does_not_invalidate_counts(self):
        good = self.status()
        bad = self.status(controlPlanePollReady=False)
        rows={'chatgpt1':good,'chatgpt2':dict(bad,account='chatgpt2')}
        result=control.fleet_status(accounts=['chatgpt1','chatgpt2'],status_reader=rows.__getitem__)
        self.assertEqual(result['accountCount'], 2)
        self.assertEqual(result['readyCount'], 1)
        self.assertFalse(result['allReady'])

if __name__ == '__main__':
    unittest.main()
