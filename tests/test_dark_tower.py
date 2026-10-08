from contextlib import redirect_stderr, redirect_stdout
import http.client
import io
import json
from pathlib import Path
import re
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from dark_tower.__main__ import main
from dark_tower.ibm import run as run_ibm
from dark_tower.portal import create_server
from dark_tower.runtime import MAX_SOURCE_BYTES, TowerError, parse, simulate


ROOT = Path(__file__).resolve().parents[1]
BELL = (ROOT / "examples" / "bell.dt").read_text(encoding="utf-8")


def program(body):
    return parse(f"fn main() {{ quantum::allocate(2); {body} quantum::measure_all(); }}")


class RuntimeTests(unittest.TestCase):
    def test_bell_and_reproducibility(self):
        result = simulate(parse(BELL), 1024, 42)
        self.assertEqual(set(result["counts"]), {"00", "11"})
        self.assertEqual(sum(result["counts"].values()), 1024)
        self.assertEqual(result, simulate(parse(BELL), 1024, 42))
        self.assertEqual(result["messages"], ["Dark Tower: Bell pair"])

    def test_gates_and_bit_order(self):
        cases = (
            ("", "00"),
            ("quantum::x(0);", "01"),
            ("quantum::x(1); quantum::cx(1, 0);", "11"),
            ("quantum::h(0); quantum::h(0);", "00"),
            ("quantum::h(0); quantum::z(0); quantum::h(0);", "01"),
            ("quantum::cx(0, 1);", "00"),
        )
        for body, expected in cases:
            with self.subTest(body=body):
                self.assertEqual(simulate(program(body), 32, 7)["counts"], {expected: 32})

    def test_comments_do_not_affect_strings(self):
        parsed = parse(BELL.replace(
            'print("Dark Tower: Bell pair");', '/* test */ print("// /* \\"quoted\\"");'
        ))
        self.assertEqual(parsed.messages, ('// /* "quoted"',))

    def test_invalid_programs(self):
        cases = (
            "", BELL + "bad", BELL.replace("allocate(2)", "allocate(13)"),
            BELL.replace("allocate(2)", "allocate(0)"),
            BELL.replace("h(0)", "h(2)"), BELL.replace("h(0)", "h(-1)"),
            BELL.replace("cx(0, 1)", "cx(0, 0)"),
            BELL.replace("h(0)", "unknown(0)"),
            BELL.replace("quantum::allocate(2);", ""),
            BELL.replace("quantum::measure_all();", ""),
            BELL.replace("quantum::h(0);", "quantum::measure_all(); quantum::h(0);"),
            BELL.replace("quantum::h(0);", "quantum::allocate(2);"),
            BELL.replace("quantum::h(0);", "let x: u32 = 0;"),
            BELL.replace("h(0)", "h(" + "1" * 5000 + ")"),
            BELL.replace("quantum::h(0);", "quantum::h(0);" * 512),
            " " * (MAX_SOURCE_BYTES + 1), None,
        )
        for source in cases:
            with self.subTest(source=str(source)[:60]):
                with self.assertRaises(TowerError):
                    parse(source)

    def test_shot_limits(self):
        for shots in (0, -1, 8193, True, 1.5, "10", None):
            with self.subTest(shots=shots), self.assertRaises(TowerError):
                simulate(parse(BELL), shots)
        self.assertEqual(sum(simulate(parse(BELL), 8192)["counts"].values()), 8192)

    def test_long_comments_and_escaped_strings(self):
        for source in ("/*" + "a/*" * 20000, '"' + '\\"' * 30000):
            with self.subTest(prefix=source[:20]), self.assertRaises(TowerError):
                parse(source)
        valid = BELL.replace(
            'print("Dark Tower: Bell pair");',
            "/*" + "a/*" * 10000 + '*/ print("' + '\\"' * 10000 + '");'
        )
        self.assertEqual(parse(valid).messages, ('"' * 10000,))

    def test_maximum_register(self):
        parsed = parse(
            "fn main() { quantum::allocate(12); quantum::x(11); quantum::measure_all(); }"
        )
        self.assertEqual(simulate(parsed, 1)["counts"], {"100000000000": 1})

    def test_cli(self):
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["run", str(ROOT / "examples" / "bell.dt"), "--shots", "16"])
        self.assertEqual(status, 0)
        self.assertEqual(sum(json.loads(output.getvalue())["counts"].values()), 16)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["run", "/nonexistent-dark-tower-source.dt"]), 1)
            self.assertEqual(main(["run", "unused.dt", "--provider", "ibm"]), 1)


class IBMTests(unittest.TestCase):
    def test_missing_credentials(self):
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(TowerError):
            run_ibm(parse(BELL), 8)

    def test_adapter(self):
        circuit = MagicMock()
        service = MagicMock()
        backend = SimpleNamespace(name="test-backend", num_qubits=127)
        service.least_busy.return_value = backend
        service.backend.return_value = backend
        sdk = MagicMock()
        sdk.QiskitRuntimeService.return_value = service
        sampler = sdk.SamplerV2.return_value
        job = sampler.run.return_value
        job.job_id.return_value = "test-job"
        job.result.return_value = [SimpleNamespace(
            data=SimpleNamespace(meas=SimpleNamespace(get_counts=lambda: {"00": 8}))
        )]
        qiskit = MagicMock()
        qiskit.QuantumCircuit.return_value = circuit
        passes = MagicMock()
        modules = {
            "qiskit": qiskit,
            "qiskit.transpiler": MagicMock(),
            "qiskit.transpiler.preset_passmanagers": passes,
            "qiskit_ibm_runtime": sdk,
        }
        with patch.dict("sys.modules", modules), patch.dict(
            "os.environ", {"IBM_QUANTUM_TOKEN": "test-placeholder",
                           "IBM_QUANTUM_INSTANCE": "test-instance"}, clear=True
        ), redirect_stderr(io.StringIO()):
            result = run_ibm(parse(BELL), 8)
            self.assertEqual(result["job_id"], "test-job")
            service.least_busy.assert_called_once_with(
                operational=True, simulator=False, min_num_qubits=2
            )
            sdk.QiskitRuntimeService.assert_called_once_with(
                channel="ibm_quantum_platform", token="test-placeholder", instance="test-instance"
            )
            circuit.h.assert_called_once_with(0)
            circuit.cx.assert_called_once_with(0, 1)
            circuit.measure_all.assert_called_once_with()
            passes.generate_preset_pass_manager.assert_called_once_with(
                backend=backend, optimization_level=1
            )
            sdk.SamplerV2.assert_called_once_with(mode=backend)
            self.assertEqual(sampler.run.call_args.kwargs, {"shots": 8})
            run_ibm(parse(BELL), 8, "chosen")
            service.backend.assert_called_once_with("chosen")
            job.result.side_effect = RuntimeError("sensitive SDK diagnostics")
            with self.assertRaises(TowerError) as error:
                run_ibm(parse(BELL), 8)
            self.assertNotIn("sensitive", str(error.exception))


class PortalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def auth_headers(self):
        status, body, headers = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        token = re.search(rb'content="([0-9a-f]{64})"', body)[1].decode()
        return {"X-Dark-Tower-Token": token, "Content-Type": "application/json"}

    def test_execution(self):
        status, body, _ = self.request(
            "POST", "/api/run", json.dumps({"source": BELL, "shots": 64}), self.auth_headers()
        )
        self.assertEqual(status, 200)
        self.assertEqual(sum(json.loads(body)["counts"].values()), 64)

    def test_security_boundaries(self):
        self.assertEqual(self.request("POST", "/api/run", "{}")[0], 403)
        self.assertEqual(self.request("GET", "/", headers={"Host": "attacker.example"})[0], 403)
        headers = self.auth_headers()
        headers["Origin"] = "https://attacker.example"
        self.assertEqual(self.request("POST", "/api/run", "{}", headers)[0], 403)
        self.assertEqual(self.request("GET", "/../../pyproject.toml")[0], 404)
        self.assertEqual(self.request("GET", "/portal.js")[0], 200)

    def test_bad_input(self):
        for body in ("[]", "{", '{"source": false}', '{"source":"bad"}',
                     json.dumps({"source": BELL, "shots": True}),
                     json.dumps({"source": BELL, "provider": "ibm"})):
            with self.subTest(body=body[:60]):
                self.assertEqual(
                    self.request("POST", "/api/run", body, self.auth_headers())[0], 400
                )
        headers = self.auth_headers()
        headers["Content-Length"] = "9999999"
        self.assertEqual(self.request("POST", "/api/run", "", headers)[0], 413)


if __name__ == "__main__":
    unittest.main()
