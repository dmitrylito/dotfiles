# Mounted into the rootless Home Assistant container (homeassistant.container) via PYTHONPATH.
# HA runs as uid 0 in a user namespace, so dbus-fast's default AUTH EXTERNAL claims uid 0 while
# the host dbus-daemon sees uid 1000 and rejects it. Leaving the uid out makes the daemon use the
# kernel's peer credentials, so BlueZ on the host system bus is reachable.
try:
    from dbus_fast import auth as _auth

    _init = _auth.AuthExternal.__init__

    def _patched_init(self, uid=None):
        _init(self, _auth.UID_NOT_SPECIFIED if uid is None else uid)

    _auth.AuthExternal.__init__ = _patched_init
except Exception:
    pass
