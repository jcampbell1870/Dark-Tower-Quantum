# Dark-Tower-Quantum

**Dark Tower** is a runnable, early-stage hosted quantum operating environment:
Dark Tower Language programs, a local state-vector simulator, an optional IBM
Quantum Platform adapter, and a Windows 11 browser connection portal.

This is **not** a bootable OS, a replacement Windows kernel, or IBM's proprietary
hardware-control software. Ordinary PCs simulate quantum circuits; real quantum
execution uses remote IBM hardware and requires your own account and quota.
The host/SDK bridge is Python because the existing DTL toolchain is a prototype.

## Start locally

Requires Python 3.12 or newer. No dependencies are needed for simulation.
Run these commands from the extracted repository directory:

```sh
python -m dark_tower run examples/bell.dt --shots 1024
python -m dark_tower portal
```

Open **http://127.0.0.1:8765** to edit or load `.dt` programs and run them.
The Bell example produces `00` and `11` counts totaling the requested shots.

## Windows 11 download and connection

1. [Download the source ZIP](https://github.com/jcampbell1870/Dark-Tower-Quantum/archive/refs/heads/main.zip)
   and extract it. This is a source distribution, not a signed installer.
2. Install [Python 3.12+](https://www.python.org/downloads/windows/).
3. Open PowerShell in the extracted folder and run:

   ```powershell
   .\windows\Start-DarkTower.ps1
   ```

4. Open the URL printed by the launcher in Edge or another browser.
   Stop with Ctrl+C. If script policy blocks the launcher, use
   `py -3 -m dark_tower portal` instead; no policy change or administrator access
   is needed.

## IBM quantum execution

IBM's public software platform is **Qiskit + IBM Quantum Runtime**, not a
downloadable quantum OS. Dark Tower uses the current Runtime `SamplerV2` API and
backend-specific ISA transpilation. It selects an accessible operational,
least-busy hardware backend, or accepts an explicit backend name; “most powerful”
depends on workload and account access, not a hard-coded processor.

```sh
python -m pip install ".[ibm]"
# Set IBM_QUANTUM_TOKEN and IBM_QUANTUM_INSTANCE in your process environment.
python -m dark_tower run examples/bell.dt --provider ibm --confirm-ibm --shots 1024
```

Hardware jobs can incur charges and queue delays. The portal deliberately
supports only local simulation and never accepts IBM credentials.

## Learn and verify

- [User manual](docs/USER-MANUAL.txt): installation, DTL quantum profile, IBM setup,
  results, troubleshooting, and security boundaries.
- [Existing Dark Tower language](https://github.com/jcampbell1870/dark-tower):
  this project implements a **documented subset plus quantum host calls**, not
  its full planned compiler, standard library, or kernel.
- [IBM getting started](https://quantum.cloud.ibm.com/docs/en/guides/hello-world)
- [IBM Runtime service](https://quantum.cloud.ibm.com/docs/en/api/qiskit-ibm-runtime/qiskit-runtime-service)
- [SamplerV2](https://quantum.cloud.ibm.com/docs/en/api/qiskit-ibm-runtime/sampler-v2)

```sh
python -m unittest discover -s tests -v
```

Tests cover DTL validation, gate semantics, sampling, CLI behavior, the IBM
adapter contract with mocked services, and portal request/security boundaries.
