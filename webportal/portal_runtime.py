"""Application-independent lifetime for the settings HTTP listener.

The main loop owns tick(). Settings only shows the connection QR code; leaving
that screen does not stop the server or tear down the setup access point.
"""
import runtime_debug
from ticks import ticks_ms, ticks_add, ticks_diff

_runtime = None


class PortalRuntime:
    def __init__(self, hardware, i18n=None):
        self.hardware = hardware
        self.i18n = i18n
        self.manager = None
        self._service = None
        self._retry_at = ticks_ms()
        self._last_error = None

    def bind(self, manager):
        self.manager = manager

    def blocked(self):
        # Writes and expensive rendering must not interrupt physical filling,
        # calibration or installation. The manager makes this decision live.
        check = getattr(self.manager, 'portal_operation_active', None)
        return bool(check and check())

    def _before_client(self):
        prepare = getattr(self.manager, 'prepare_portal_client', None)
        if prepare:
            return prepare()
        return False

    def service(self):
        if self._service is None:
            from webportal.setup_portal_service import SetupPortalService
            self._service = SetupPortalService(
                wifi_device=self.hardware.wifi, scale_device=self.hardware.scale,
                debug=runtime_debug.DEBUG, i18n=self.i18n,
                before_client=self._before_client, operations_blocked=self.blocked)
        return self._service

    def leave_settings(self):
        # A temporary Wi-Fi test still must not silently become permanent.
        # Keep the HTTP socket/AP alive while restoring the saved station.
        service = self._service
        if service and service._wifi_test:
            service._wifi_test.restore()
            service._wifi_test = None

    def tick(self):
        service = self._service
        try:
            if service is None or service._listener is None:
                if self.blocked() or ticks_diff(ticks_ms(), self._retry_at) < 0:
                    return
                wifi = getattr(self.hardware, 'wifi', None)
                if wifi is None or not wifi.connected():
                    return
                # On normal boot start automatically as soon as the home
                # network is ready, even if Settings was never opened.
                service = self.service()
                service.start_or_resume()
            service.tick()
            self._last_error = None
        except Exception as error:
            kind = type(error).__name__
            if kind != self._last_error:
                runtime_debug.log('[portal] background error: {}', kind)
            self._last_error = kind
            self._retry_at = ticks_add(ticks_ms(), 5000)


def get_runtime(hardware=None, i18n=None):
    global _runtime
    if _runtime is None:
        if hardware is None:
            raise RuntimeError('Portal runtime needs hardware on first use')
        _runtime = PortalRuntime(hardware, i18n)
    return _runtime
