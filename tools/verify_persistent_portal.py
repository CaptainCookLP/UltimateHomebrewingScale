"""Persistent portal lifecycle: python tools/verify_persistent_portal.py."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app_registry
from webportal import portal_runtime, portal_routes, setup_portal_service
from apps.settings_app import SettingsApp


def manager_type():
    spec=importlib.util.spec_from_file_location('_persistent_manager',ROOT/'core/app_manager.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AppManager


class FakeService:
    def __init__(self, **kwargs):
        self.kwargs=kwargs
        self._listener=None
        self._wifi_test=None
        self.calls=0
        self.starts=0
    def start_or_resume(self):
        self.starts+=1
        self._listener=object()
        return {'url':'http://192.168.1.42:8080/'}
    def tick(self):
        self.calls+=1
    def stop(self):
        raise AssertionError('Persistent service must not be stopped by Settings')


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.connected=False
        self.hardware=types.SimpleNamespace(wifi=types.SimpleNamespace(connected=lambda:self.connected), scale=None)
        self.runtime=portal_runtime.PortalRuntime(self.hardware)
        self.factory=patch.object(setup_portal_service,'SetupPortalService',side_effect=lambda **kw:FakeService(**kw))
        self.factory_mock=self.factory.start()
        self.addCleanup(self.factory.stop)

    def test_starts_automatically_after_normal_wifi_connection(self):
        self.runtime.tick()
        self.factory_mock.assert_not_called()
        self.connected=True
        self.runtime.tick()
        service=self.runtime._service
        self.assertEqual(service.starts,1)
        self.assertEqual(service.calls,1)
        self.runtime.tick()
        self.assertEqual(service.starts,1)
        self.assertEqual(service.calls,2)

    def test_setup_ap_keeps_running_without_a_home_wifi_connection(self):
        service=self.runtime.service()
        service.start_or_resume()
        self.assertFalse(self.connected)
        self.runtime.tick()
        self.assertEqual(service.calls,1)
        self.assertIs(self.runtime.service(),service)

    def test_leaving_settings_keeps_socket_but_restores_unsaved_test(self):
        service=self.runtime.service()
        service.start_or_resume()
        listener=service._listener
        test=types.SimpleNamespace(restore=Mock())
        service._wifi_test=test
        self.runtime.leave_settings()
        self.assertIs(service._listener,listener)
        test.restore.assert_called_once()
        self.assertIsNone(service._wifi_test)

    def test_no_new_portal_allocations_during_protected_operation(self):
        self.connected=True
        self.runtime.bind(types.SimpleNamespace(portal_operation_active=lambda:True))
        self.runtime.tick()
        self.factory_mock.assert_not_called()

    def test_settings_exit_does_not_stop_shared_server(self):
        with patch.object(portal_runtime,'_runtime',self.runtime):
            service=self.runtime.service()
            service.start_or_resume()
            app=object.__new__(SettingsApp)
            app._events=None
            app._portal=service
            app.hardware=self.hardware
            app.i18n=None
            app._screen=object()
            app.on_exit()
            self.assertIsNotNone(service._listener)
            self.runtime.tick()
            self.assertEqual(service.calls,1)

    def test_current_app_controls_display_cleanup_not_old_settings_object(self):
        prepare=Mock()
        manager=types.SimpleNamespace(prepare_portal_client=prepare,portal_operation_active=lambda:False)
        self.runtime.bind(manager)
        self.runtime.service().kwargs['before_client']()
        prepare.assert_called_once()


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.Manager=manager_type()
        self.manager=object.__new__(self.Manager)
        self.callback=Mock()
        self.manager._apps={app_registry.SETTINGS:types.SimpleNamespace(_release_screen_for_portal_client=self.callback)}

    def test_weighing_display_is_never_released_by_browser(self):
        for app in (app_registry.LAUNCHER,app_registry.SCALE,app_registry.MALT,app_registry.HOP,app_registry.KEG):
            self.manager._active_app_id=app
            self.manager.prepare_portal_client()
        self.callback.assert_not_called()
        self.manager._active_app_id=app_registry.SETTINGS
        self.manager.prepare_portal_client()
        self.callback.assert_called_once()

    def test_physical_operations_lock_settings(self):
        for app in (app_registry.KEG,app_registry.CALIBRATION_WIZARD,app_registry.UPDATER):
            self.manager._active_app_id=app
            self.assertTrue(self.manager.portal_operation_active())
        self.manager._active_app_id=app_registry.SCALE
        self.assertFalse(self.manager.portal_operation_active())

    def test_busy_routes_refuse_save_wifi_tests_and_heavy_pages(self):
        replies=[]
        service=types.SimpleNamespace(operations_blocked=lambda:True,
            _send=lambda client,status=200,content_type='',body='',**kw:replies.append((status,body)))
        for method,path in [('POST','/save'),('POST','/restore'),('POST','/wifi/test'),('POST','/simulation/weight'),('GET','/')]:
            portal_routes.handle_request(service,None,method,path,'')
            self.assertEqual(replies[-1][0],409)
            self.assertIn('operation_in_progress',replies[-1][1])
        portal_routes.handle_request(service,None,'GET','/health','')
        self.assertEqual(replies[-1],(200,'{"ok":true}'))

    def test_pending_restart_waits_for_physical_operation(self):
        blocked=True
        service=setup_portal_service.SetupPortalService(operations_blocked=lambda:blocked)
        service._listener=types.SimpleNamespace(accept=Mock(side_effect=OSError()))
        service._reboot_after_response=True
        service._reboot=Mock()
        # No active client: tick must also handle pending reboot after accept()
        # would block, without losing it when the physical operation is active.
        service.tick()
        service._reboot.assert_not_called()
        self.assertTrue(service._reboot_after_response)
        blocked=False
        service.tick()
        service._reboot.assert_called_once()
        self.assertFalse(service._reboot_after_response)

    def test_web_request_outside_settings_does_not_force_gc_or_release_screen(self):
        service=setup_portal_service.SetupPortalService(before_client=lambda:False)
        with patch('gc.collect') as collect:
            service._run_before_client()
        collect.assert_not_called()

    def test_settings_modules_are_not_evicted_on_app_switch(self):
        spec=importlib.util.spec_from_file_location('_persistent_module',ROOT/'core/app_manager.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for name in ('webportal.portal_runtime','webportal.setup_portal_service','webportal.portal_routes','webportal.request_limits'):
            self.assertNotIn(name,module._COMPANION_MODULES)


if __name__=='__main__':
    unittest.main(verbosity=2)
