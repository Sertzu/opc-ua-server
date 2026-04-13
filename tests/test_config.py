from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from opc_ua_server.config import ConfigError, load_app_config


class ConfigLoadingTests(unittest.TestCase):
    def test_relative_certificate_paths_are_resolved_from_the_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    logging:
                      level: DEBUG
                    certificates:
                      root: ./certs
                    address_space:
                      nodes:
                        - type: folder
                          browse_name: Demo
                          children:
                            - type: variable
                              browse_name: Temperature
                              value: 10.5
                              variant_type: Double
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            config = load_app_config(config_path)

            self.assertEqual(config.logging_level, "DEBUG")
            self.assertEqual(config.certificates.root, (Path(temp_dir) / "certs").resolve())
            self.assertEqual(
                config.certificates.server_certificate,
                (Path(temp_dir) / "certs" / "server" / "server_cert.pem").resolve(),
            )
            self.assertEqual(config.address_space.nodes[0].children[0].browse_name, "Temperature")

    def test_no_security_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    server:
                      security_policies:
                        - NoSecurity
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ConfigError):
                load_app_config(config_path)