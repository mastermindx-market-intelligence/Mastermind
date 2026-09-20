import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import studio_direct_control as control


class ControlTests(unittest.TestCase):
    def test_start_and_stop_order_keep_one_explicit_account(self):
        for action, expected in [('start', ['private_service.py', 'private_tunnel_service.py']),
                                 ('stop', ['private_tunnel_service.py', 'private_service.py'])]:
            with self.subTest(action=action), patch.object(control, 'invoke', return_value={'running':True,'ready':True}) as invoke:
                control.operate(action, 'chatgpt3')
                self.assertEqual([c.args[0] for c in invoke.call_args_list[:2]], expected)
                self.assertTrue(all(c.args[2] == 'chatgpt3' for c in invoke.call_args_list))

    def test_gateway_start_failure_does_not_start_tunnel(self):
        with patch.object(control, 'invoke', side_effect=RuntimeError('gateway failed')) as invoke:
            with self.assertRaises(RuntimeError):
                control.operate('start', 'chatgpt1')
            self.assertEqual(invoke.call_count, 1)

    def test_status_never_mutates_and_requires_both_components(self):
        with patch.object(control, 'invoke', side_effect=[{'running': True}, {'ready': False}]) as invoke:
            result = control.operate('status', 'chatgpt1')
            self.assertFalse(result['ready'])
            self.assertTrue(all(c.args[1] == 'status' for c in invoke.call_args_list))

    def test_start_waits_for_tunnel_readiness(self):
        with patch.object(control, 'invoke', side_effect=[{}, {}, {'running':True}, {'ready':False}, {'running':True}, {'ready':True}]), patch.object(control.time,'sleep') as sleep:
            self.assertTrue(control.operate('start','chatgpt1')['ready'])
            sleep.assert_called_once()

    def test_start_fails_when_readiness_deadline_expires(self):
        with patch.object(control, 'invoke', return_value={'running':True,'ready':False}), patch.object(control.time,'monotonic',side_effect=[0,36]):
            with self.assertRaisesRegex(RuntimeError,'did not become ready'):
                control.operate('start','chatgpt1')

    def test_installed_accounts_reads_only_owned_private_install_manifests(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name in ('chatgpt3', 'chatgpt1'):
                account = root / name
                account.mkdir()
                (account / 'manifest.json').write_text('{}')
            (root / 'chatgpt2').mkdir()
            invalid = root / 'ChatGPT4'
            invalid.mkdir()
            (invalid / 'manifest.json').write_text('{}')
            self.assertEqual(control.installed_accounts(root), ['chatgpt1', 'chatgpt3'])

    def test_fleet_status_is_read_only_and_aggregates_all_installed_accounts(self):
        states = {
            'chatgpt1': {'account':'chatgpt1','ready':True,'gateway':{'runtimeVersion':'0.1.5'},'tunnel':{'ready':True}},
            'chatgpt2': {'account':'chatgpt2','ready':True,'gateway':{'runtimeVersion':'0.1.6'},'tunnel':{'ready':True}},
        }
        with patch.object(control, 'installed_accounts', return_value=['chatgpt1','chatgpt2']), \
             patch.object(control, 'operate', side_effect=lambda action, account: states[account]) as operate:
            result = control.fleet_status()
        self.assertTrue(result['allReady'])
        self.assertEqual(result['readyCount'], 2)
        self.assertEqual([row['account'] for row in result['accounts']], ['chatgpt1','chatgpt2'])
        self.assertTrue(all(call.args[0] == 'status' for call in operate.call_args_list))

    def test_fleet_status_preserves_one_seat_failure_without_hiding_healthy_seats(self):
        def status(action, account):
            if account == 'chatgpt2':
                raise RuntimeError('tunnel unavailable')
            return {'account':account,'ready':True,'gateway':{},'tunnel':{}}
        with patch.object(control, 'installed_accounts', return_value=['chatgpt1','chatgpt2','chatgpt3']), \
             patch.object(control, 'operate', side_effect=status):
            result = control.fleet_status()
        self.assertFalse(result['allReady'])
        self.assertEqual(result['readyCount'], 2)
        self.assertEqual(result['accounts'][1], {
            'account':'chatgpt2', 'ready':False, 'error':'tunnel unavailable'
        })


if __name__ == '__main__':
    unittest.main()
