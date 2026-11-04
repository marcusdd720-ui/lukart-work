"""A dedicated LEGAL OS CLI switch must not change default legacy behavior."""
from unittest import TestCase
from unittest.mock import patch
from pathlib import Path
from lukart_work import operator_host


class CliTests(TestCase):
    def test_legal_os_switch_is_propagated_to_host(self):
        class FakeServer:
            server_port = 8786
            closed = False
            def serve_forever(self):
                return None
            def server_close(self):
                self.closed = True
        server = FakeServer()
        arguments = ["operator_host.py", "--config", "synthetic-config.py",
                     "--port", "8786", "--legal-os"]
        with patch("sys.argv", arguments), \
             patch.object(operator_host.runpy, "run_path",
                          return_value={"build_operator": lambda: object()}), \
             patch.object(operator_host, "create_server",
                          return_value=server) as create:
            operator_host.main()
        self.assertTrue(create.call_args.kwargs["case_only"])
        self.assertTrue(server.closed)
        self.assertEqual(create.call_args.args[1], 8786)

    def test_without_switch_preserves_default_mode(self):
        class FakeServer:
            server_port = 8765
            def serve_forever(self): pass
            def server_close(self): pass
        with patch("sys.argv", ["operator_host.py","--config","synthetic-config.py"]), \
             patch.object(operator_host.runpy,"run_path",
                          return_value={"build_operator":lambda:object()}), \
             patch.object(operator_host,"create_server",return_value=FakeServer()) as create:
            operator_host.main()
        self.assertFalse(create.call_args.kwargs["case_only"])


if __name__ == "__main__":
    import unittest
    unittest.main()
