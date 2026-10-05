"""Regression tests for real Paramiko host-key checks, without network access."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import paramiko
from test_lib.common import SshClient


class SshHostKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ephemeral test keys: no user keys or credentials are read or stored.
        cls.server_key = paramiko.RSAKey.generate(2048)
        cls.other_key = paramiko.RSAKey.generate(2048)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.system_file = self.root / "system_known_hosts"
        self.custom_file = self.root / "custom_known_hosts"
        self.system_file.write_text("", encoding="utf-8")
        self.custom_file.write_text("", encoding="utf-8")
        self.transport = Mock()
        self.transport.get_remote_server_key.return_value = self.server_key
        self.transport.get_security_options.return_value.key_types = [
            "rsa-sha2-512", "rsa-sha2-256", "ssh-rsa"
        ]
        original_client = paramiko.SSHClient
        system_file = self.system_file
        transport = self.transport

        class OfflineClient(original_client):
            def load_system_host_keys(self, filename=None):
                return super().load_system_host_keys(str(system_file))

            def connect(self, hostname, **kwargs):
                # Only transport and authentication are mocked. Paramiko's
                # connect(), host-file parsing and policies run unchanged.
                return super().connect(
                    hostname, sock=Mock(),
                    transport_factory=lambda *args, **kw: transport, **kwargs
                )

        self.auth = Mock()
        self.addCleanup(patch.stopall)
        patch.object(OfflineClient, "_auth", self.auth).start()
        patch("test_lib.common.paramiko.SSHClient", OfflineClient).start()
        patch.dict(os.environ, {"SSH_KNOWN_HOSTS": ""}).start()

    def trust(self, path, key):
        path.write_text(
            f"ssh-test.invalid {key.get_name()} {key.get_base64()}\n",
            encoding="utf-8",
        )

    def connect(self):
        return SshClient("ssh-test.invalid", "test-user", password="test-only")

    def test_unknown_key_rejected_before_authentication(self):
        with self.assertRaisesRegex(paramiko.SSHException, "not found in known_hosts"):
            self.connect()
        self.auth.assert_not_called()
        self.transport.close.assert_called_once()

    def test_system_known_key_accepted(self):
        self.trust(self.system_file, self.server_key)
        client = self.connect()
        self.auth.assert_called_once()
        client.close()

    def test_custom_known_key_accepted(self):
        self.trust(self.custom_file, self.server_key)
        os.environ["SSH_KNOWN_HOSTS"] = str(self.custom_file)
        client = self.connect()
        self.auth.assert_called_once()
        client.close()

    def test_custom_file_does_not_accept_unknown_key(self):
        os.environ["SSH_KNOWN_HOSTS"] = str(self.custom_file)
        with self.assertRaises(paramiko.SSHException):
            self.connect()
        self.auth.assert_not_called()

    def test_changed_key_rejected_before_authentication(self):
        self.trust(self.custom_file, self.other_key)
        os.environ["SSH_KNOWN_HOSTS"] = str(self.custom_file)
        with self.assertRaises(paramiko.BadHostKeyException):
            self.connect()
        self.auth.assert_not_called()
        self.transport.close.assert_called_once()

    def test_custom_file_cannot_override_system_key(self):
        self.trust(self.system_file, self.other_key)
        self.trust(self.custom_file, self.server_key)
        os.environ["SSH_KNOWN_HOSTS"] = str(self.custom_file)
        with self.assertRaises(paramiko.BadHostKeyException):
            self.connect()
        self.auth.assert_not_called()

    def test_missing_custom_file_fails_before_connection(self):
        os.environ["SSH_KNOWN_HOSTS"] = str(self.root / "missing")
        with self.assertRaises(OSError):
            self.connect()
        self.transport.start_client.assert_not_called()
        self.auth.assert_not_called()

    def test_malformed_custom_file_fails_before_connection(self):
        self.custom_file.write_text("ssh-test.invalid ssh-rsa a\n", encoding="utf-8")
        os.environ["SSH_KNOWN_HOSTS"] = str(self.custom_file)
        with self.assertRaises(paramiko.hostkeys.InvalidHostKey):
            self.connect()
        self.transport.start_client.assert_not_called()
        self.auth.assert_not_called()


if __name__ == "__main__":
    unittest.main()
