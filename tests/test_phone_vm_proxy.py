from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import phone_vm_proxy as proxy

CONFIG = proxy.Config(adb_host="192.0.2.1", adb_port=54321)


class ConfigTests(unittest.TestCase):
    def test_rejects_invalid_settings(self):
        for data in ({"token": "unused"}, [], {"adb_host": "$(id)"}, {"adb_host": "-option"},
                     {"adb_port": True}, {"phone_port": 0}, {"vm_port": 65536}, {"vm_port": 5037},
                     {"vm_port": 3773}, {"vm_port": 1455}, {"adb_port": 10808}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                proxy.Config.parse(data)

    def test_gateway_failure_does_not_guess_a_phone_address(self):
        with patch.object(proxy, "run", return_value=(0, "")), self.assertRaisesRegex(RuntimeError, "--host"):
            proxy.endpoint(proxy.Config(adb_port=54321))

    def test_explicit_ipv6_address_is_bracketed(self):
        config = proxy.Config.parse({"adb_host": "2001:db8::1", "adb_port": 54321})
        self.assertEqual(proxy.endpoint(config), "[2001:db8::1]:54321")

    def test_saved_shell_and_service_environments_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            proxy.save_config(directory, CONFIG)
            self.assertEqual(proxy.read_config(directory), CONFIG)
            exports = (directory / "env.sh").read_text(encoding="utf-8").splitlines()[1:]
            parsed = dict(line.removeprefix("export ").replace("'", "").split("=", 1) for line in exports)
            self.assertEqual(parsed, proxy.environment(CONFIG))
            self.assertEqual(parsed["HTTPS_PROXY"], "http://127.0.0.1:18080")
            self.assertEqual(parsed["NO_PROXY"], "localhost,127.0.0.1,::1")
            if os.name != "nt":
                for name in ("config.json", "env.sh"):
                    self.assertEqual((directory / name).stat().st_mode & 0o777, 0o600)


class ListenerTests(unittest.TestCase):
    def test_accepts_ipv4_and_ipv6_loopback_only(self):
        output = "LISTEN 0 128 127.0.0.1:18080 0.0.0.0:*\nLISTEN 0 128 [::1]:18080 [::]:*"
        with patch.object(proxy, "run", return_value=(0, output)):
            proxy.verify_loopback(18080)

    def test_rejects_missing_wildcard_and_nonloopback_listeners(self):
        for output in ("", "LISTEN 0 128 0.0.0.0:18080 0.0.0.0:*",
                       "LISTEN 0 128 [::]:18080 [::]:*", "LISTEN 0 128 192.0.2.2:18080 0.0.0.0:*",
                       "LISTEN 0 128 127.0.0.1:18080 0.0.0.0:*\nLISTEN 0 128 *:18080 *:*"):
            with self.subTest(output=output), patch.object(proxy, "run", return_value=(0, output)), \
                    self.assertRaises(RuntimeError):
                proxy.verify_loopback(18080)


class ForwardTests(unittest.TestCase):
    def test_new_mapping_does_not_rebind_existing_ports(self):
        with patch.object(proxy, "adb", side_effect=[(0, "device"), (0, ""), (0, "")]) as adb, \
                patch.object(proxy, "verify_loopback"):
            proxy.cycle(CONFIG)
        self.assertEqual(adb.call_args_list[-1].args, ("forward", "--no-rebind", "tcp:18080", "tcp:10808"))
        self.assertEqual(adb.call_args_list[-1].kwargs, {"device": "192.0.2.1:54321"})

    def test_same_mapping_is_kept_and_rechecked(self):
        row = "192.0.2.1:54321 tcp:18080 tcp:10808"
        with patch.object(proxy, "adb", side_effect=[(0, "device"), (0, row)]) as adb, \
                patch.object(proxy, "verify_loopback") as verify:
            proxy.cycle(CONFIG)
        self.assertEqual(adb.call_count, 2)
        verify.assert_called_once_with(18080)

    def test_other_device_or_destination_is_never_replaced(self):
        for row in ("192.0.2.2:54321 tcp:18080 tcp:10808", "192.0.2.1:54321 tcp:18080 tcp:9000"):
            with self.subTest(row=row), patch.object(proxy, "adb", side_effect=[(0, "device"), (0, row)]) as adb, \
                    self.assertRaisesRegex(RuntimeError, "another ADB forward"):
                proxy.cycle(CONFIG)
            self.assertEqual(adb.call_count, 2)

    def test_unavailable_device_does_not_claim_success(self):
        with patch.object(proxy, "adb", side_effect=[(1, "offline"), (0, "unable"), (1, "offline")]) as adb, \
                self.assertRaisesRegex(RuntimeError, "Wireless ADB unavailable"):
            proxy.cycle(CONFIG)
        self.assertEqual(adb.call_args_list[1].args, ("connect", "192.0.2.1:54321"))
        self.assertEqual(adb.call_count, 3)

    def test_failed_forward_listing_does_not_create_a_mapping(self):
        with patch.object(proxy, "adb", side_effect=[(0, "device"), (1, "failed")]) as adb, \
                self.assertRaisesRegex(RuntimeError, "Cannot list"):
            proxy.cycle(CONFIG)
        self.assertEqual(adb.call_count, 2)

    def test_new_nonloopback_forward_is_removed(self):
        with patch.object(proxy, "adb", side_effect=[(0, "device"), (0, ""), (0, "")]), \
                patch.object(proxy, "verify_loopback", side_effect=RuntimeError("nonloopback")), \
                patch.object(proxy, "cleanup") as cleanup, self.assertRaisesRegex(RuntimeError, "nonloopback"):
            proxy.cycle(CONFIG)
        cleanup.assert_called_once_with(CONFIG)

    def test_cleanup_only_removes_the_exact_mapping(self):
        for row in ("192.0.2.1:54321 tcp:18080 tcp:10808", "192.0.2.2:54321 tcp:18080 tcp:10808",
                    "192.0.2.1:54321 tcp:18080 tcp:9999"):
            exact = row.endswith("54321 tcp:18080 tcp:10808") and row.startswith("192.0.2.1:")
            with self.subTest(row=row), patch.object(proxy, "adb", return_value=(0, row)) as adb:
                proxy.cleanup(CONFIG)
            self.assertEqual(adb.call_count, 2 if exact else 1)
            if exact:
                self.assertEqual(adb.call_args.args, ("forward", "--remove", "tcp:18080"))


class CommandTests(unittest.TestCase):
    def test_configure_refuses_to_race_a_running_or_stopping_daemon(self):
        for code, state in ((0, "active"), (3, "activating"), (3, "deactivating"), (1, "error")):
            with self.subTest(state=state), patch.object(proxy, "run", return_value=(code, state)), \
                    self.assertRaises(RuntimeError):
                proxy.require_stopped()

    def test_new_connection_port_preserves_other_settings(self):
        original = proxy.Config(adb_host="192.0.2.1", adb_port=50000, phone_port=8080, vm_port=18081)
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            directory = home / ".config/android-vm-proxy"
            proxy.save_config(directory, original)
            with patch.object(Path, "home", return_value=home), patch.object(proxy, "require_stopped"), \
                    patch.object(proxy, "cleanup") as cleanup, redirect_stdout(io.StringIO()):
                self.assertEqual(proxy.main(["configure", "54321"]), 0)
            self.assertEqual(proxy.read_config(directory), proxy.Config("192.0.2.1", 54321, 8080, 18081))
            cleanup.assert_called_once_with(original)


if __name__ == "__main__":
    unittest.main()
