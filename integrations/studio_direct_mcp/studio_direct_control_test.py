import unittest
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


if __name__ == '__main__':
    unittest.main()
