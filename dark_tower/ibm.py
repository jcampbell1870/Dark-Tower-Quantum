"""Optional IBM Quantum Platform adapter; credentials never enter the portal."""

import os
import sys

from .runtime import TowerError, validate_shots


def run(program, shots, backend_name=None):
    validate_shots(shots)
    token = os.environ.get("IBM_QUANTUM_TOKEN")
    instance = os.environ.get("IBM_QUANTUM_INSTANCE")
    if not token or not instance:
        raise TowerError("Set IBM_QUANTUM_TOKEN and IBM_QUANTUM_INSTANCE first.")
    try:
        from qiskit import QuantumCircuit
        from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
        from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
    except ImportError as exc:
        raise TowerError("Install IBM support with: python -m pip install '.[ibm]'") from exc
    try:
        service = QiskitRuntimeService(
            channel="ibm_quantum_platform", token=token, instance=instance
        )
        backend = (
            service.backend(backend_name)
            if backend_name
            else service.least_busy(
                operational=True, simulator=False, min_num_qubits=program.qubits
            )
        )
        if backend.num_qubits < program.qubits:
            raise TowerError("Selected backend has insufficient qubits.")
        circuit = QuantumCircuit(program.qubits)
        for gate, args in program.operations:
            getattr(circuit, gate)(*args)
        circuit.measure_all()
        manager = generate_preset_pass_manager(backend=backend, optimization_level=1)
        job = SamplerV2(mode=backend).run([manager.run(circuit)], shots=shots)
        job_id = job.job_id()
        print(f"Submitted IBM job {job_id}; waiting for results.", file=sys.stderr)
        result = job.result()[0]
        return {
            "provider": "ibm",
            "backend": backend.name,
            "job_id": job_id,
            "qubits": program.qubits,
            "shots": shots,
            "counts": result.data.meas.get_counts(),
            "messages": list(program.messages),
        }
    except TowerError:
        raise
    except Exception:
        # SDK exception text can contain credential-bearing HTTP diagnostics.
        raise TowerError(
            "IBM execution failed. Check credentials, instance, backend access, and quota "
            "in IBM Quantum Platform. Submitted jobs may remain active there."
        ) from None
