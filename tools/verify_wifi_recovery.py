"""Late WLAN connection recovery: python tools/verify_wifi_recovery.py."""
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from apps.wifi_problem_app import WifiProblemApp


class WifiRecoveryTests(unittest.TestCase):
    def app(self, connected, pressed):
        app=object.__new__(WifiProblemApp)
        app.hardware=types.SimpleNamespace(
            wifi=types.SimpleNamespace(connected=lambda:connected),
            button=types.SimpleNamespace(was_short_pressed=Mock(return_value=pressed)))
        app._restart_on_setup_access_point=Mock()
        return app

    def test_late_dhcp_returns_to_launcher_without_button(self):
        app=self.app(True,False)
        self.assertEqual(app.tick(),'launcher')
        app._restart_on_setup_access_point.assert_not_called()

    def test_late_dhcp_does_not_reboot_even_if_ok_was_pressed(self):
        app=self.app(True,True)
        self.assertEqual(app.tick(),'launcher')
        app._restart_on_setup_access_point.assert_not_called()
        app.hardware.button.was_short_pressed.assert_called_once()

    def test_offline_ok_keeps_existing_setup_recovery(self):
        app=self.app(False,True)
        self.assertIsNone(app.tick())
        app._restart_on_setup_access_point.assert_called_once()

    def test_offline_page_waits_for_user(self):
        app=self.app(False,False)
        self.assertIsNone(app.tick())
        app._restart_on_setup_access_point.assert_not_called()


if __name__=='__main__':
    unittest.main(verbosity=2)
