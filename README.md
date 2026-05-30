# NISQ-Era Quantum Image Processing & Cryptographic Protocol Suite

[![Interactive Dashboard](https://img.shields.io/badge/Interactive_Dashboard-Live_Simulation-58a6ff?style=for-the-badge&logo=github)](https://quantumlyquinny.github.io/NISQ-Quantum-Image-Processing/)
[![IBM Quantum](https://img.shields.io/badge/Executed_On-IBM_Quantum_Hardware-6929EE?style=for-the-badge&logo=ibm)](https://quantum.ibm.com/)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python)](https://python.org)
[![Qiskit](https://img.shields.io/badge/Qiskit-SamplerV2-purple?style=for-the-badge)](https://qiskit.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

> **This project was executed on physical IBM superconducting quantum processors (Eagle r3 architecture) via Qiskit Runtime SamplerV2 primitives — not just simulated.**

---

## Abstract

This repository explores the physical and computational trade-offs of transmitting classical image data across Noisy Intermediate-Scale Quantum (NISQ) channels. Moving beyond standard QKD textbook circuits, this project implements a **comparative suite of four quantum encoding protocols** to evaluate three critical engineering vectors simultaneously: **Data Efficiency**, **Transmission Security**, and **Verification Integrity**.

The central thesis is that in the NISQ era, no single protocol optimises all three vectors — and the goal of this suite is to make those trade-offs quantitatively visible, both under local Aer simulation with injected depolarising noise and under authentic hardware drift on real IBM quantum processors.

---

## Why This Project Exists

Most quantum computing coursework stops at simulating known protocols in noise-free environments. Real quantum hardware is fundamentally different: gate errors, decoherence, measurement fidelity degradation, and crosstalk between qubits make theoretical fidelity a ceiling, not a guarantee.

This suite was built to answer a practical engineering question: **given a classical image payload and a NISQ-era quantum channel, which encoding architecture survives — and at what cost?**

---

## The Protocol Suite

In the NISQ era, quantum engineers cannot optimise for every variable simultaneously. Each protocol in this suite represents a deliberate architectural choice with explicit trade-offs.

### 1. Basis Encoding — The Baseline

**Objective:** Direct 1:1 mapping of classical pixels to physical qubits via Pauli-X gates.

**The Physics:** Each pixel value maps to a single qubit state — the simplest possible encoding. Circuit depth is minimal (single-qubit gates only), making this the most noise-resilient architecture.

**The Trade-off:** Resilience comes at a severe hardware cost. A 16-pixel image requires 16 physical qubits — this scales linearly and becomes prohibitively expensive for real image payloads. This is the control condition against which every other protocol is measured.

---

### 2. Entangled Transmission — The Security Route

**Objective:** Tamper-evident payload transmission using entangled Bell pairs, inspired by E91 QKD.

**The Physics:** The payload is encoded into one half of an entangled pair. Environmental decoherence or third-party measurement degrades entanglement, producing a measurable increase in Quantum Bit Error Rate (QBER). Any QBER above the ~11% threshold statistically proves channel compromise.

**The Trade-off:** Doubles the required qubit count, adds moderate circuit depth through CNOT gates, but provides the only mathematically provable tamper-detection mechanism in the suite. Security is not assumed — it is physically enforced.

---

### 3. Quantum Watermarking — The Verification Route

**Objective:** Payload integrity verification via fragile superposition sentinels, without additional qubit overhead.

**The Physics:** Specific "sentinel" pixels are placed into superposition using Hadamard gates. Because measuring a quantum state forces wave-function collapse, any unauthorised observation of the payload permanently destroys the watermark — alerting the receiver to a compromised channel. This is a direct application of quantum steganography principles.

**The Trade-off:** Zero additional qubit cost and low circuit depth, but the sentinel indices become hyper-sensitive to natural channel noise on NISQ hardware — making false positives a real engineering concern at scale.

---

### 4. Amplitude Encoding — The Efficiency Route

**Objective:** Exponential spatial compression — encode an N-pixel image into log₂(N) qubits.

**The Physics:** Classical pixel values are normalised and mapped directly onto qubit probability amplitudes. A 16-pixel image compresses into 4 qubits — a 4× reduction in hardware requirements that scales logarithmically.

**The Trade-off:** This is the most theoretically powerful encoding and the most practically fragile. Arbitrary state preparation compiles into dense CNOT gate networks, producing severe circuit depth. On NISQ hardware, this depth acts as an error multiplier — the image payload degrades significantly even under moderate noise conditions, as the hardware execution results confirm.

---

## Quantitative Protocol Comparison

| Protocol | Qubit Cost (4×4 image) | Primary Gates | Circuit Depth | Expected Physical QBER | NISQ Viability |
|:---|:---:|:---:|:---:|:---:|:---:|
| Basis Encoding | 16 | `X` | Very Low | ~0.00% | 🟢 Excellent |
| Entangled Transmission | 32 | `H`, `CX` | Moderate | ~18.75% | 🟡 Moderate |
| Quantum Watermarking | 16 | `H`, `X` | Low | ~12.50% | 🟢 High |
| Amplitude Encoding | **4** | State Prep | **Severe** | ~25.00%+ | 🔴 Fragile |

*Expected Physical QBER reflects performance under high-noise physical channel conditions.*  
*See the [Interactive Dashboard](https://quantumlyquinny.github.io/NISQ-Quantum-Image-Processing/) for live simulation results and noise comparison plots.*

---

## Hardware Execution

This repository uses **Qiskit Runtime Primitives (SamplerV2)** for physical QPU execution — not legacy `execute()` calls.

**Simulation Phase:** Local execution via `qiskit_aer` with custom `NoiseModel` configurations injecting depolarising errors, channel degradation, and wave-function collapse to model NISQ conditions before hardware submission.

**Physical Execution:** Authenticates via IBM Cloud, transpiles circuits to the target backend's native gate set, and deploys to the least busy operational QPU (tested on `ibm_marrakesh` — Eagle r3 architecture), capturing authentic environmental noise, hardware drift, and measurement fidelity metrics across thousands of shots.

The hardware results visible in the Interactive Dashboard represent authentic QPU output — not post-processed simulation data.

---

## Interactive Dashboard

**[Launch Dashboard →](https://quantumlyquinny.github.io/NISQ-Quantum-Image-Processing/)**

The live dashboard visualises:
- **Noise Comparison** — protocol fidelity under simulation vs. real hardware conditions
- **QBER Measurements** — entangled transmission error rates with and without injected noise
- **Amplitude Reconstruction** — original payload vs. hardware-reconstructed image, illustrating NISQ degradation
- **Circuit Depth Comparison** — the efficiency vs. security trade-off made quantitatively visible

---

## Theoretical Foundations

This architecture bridges classical computer vision with quantum cryptography across four research domains:

**Quantum Image Encoding**
- Zhang, Y., et al. (2013). *NEQR: A novel enhanced quantum representation of digital images.* Quantum Information Processing, 12(8), 2833–2860. — Foundational logic for mapping classical pixel arrays into quantum states.
- Le, P. Q., et al. (2011). *A flexible representation of quantum images for polynomial preparation, image compression, and processing operations.* Quantum Information Processing. — Mathematical basis for amplitude normalisation and FRQI encoding.
- Möttönen, M., et al. (2004). *Decomposition of arbitrary unitary matrices.* — Explains the dense CNOT scaling that limits amplitude encoding on NISQ devices.

**Quantum Security & Cryptography**
- Bennett, C. H., & Brassard, G. (1984). *Quantum cryptography: Public key distribution and coin tossing.* — Foundational mechanics of wave-function collapse for secure key sifting.
- Ekert, A. K. (1991). *Quantum cryptography based on Bell's theorem.* Physical Review Letters. — Theoretical backbone of the entangled transmission protocol.
- Qu, Z., et al. (2016). *A novel quantum image steganography algorithm based on exploiting modification direction.* — Guides the superposition sentinel implementation in quantum watermarking.

**Post-Quantum Context**
- Bos, J., et al. (2018). *CRYSTALS-Kyber: a CCA-secure module-lattice-based KEM.* IEEE EuroS&P. — Acknowledges the hybrid future: physical QKD protocols must coexist with NIST-standardised lattice-based cryptography (ML-KEM) to defend against Shor's Algorithm.

**Hardware Realities**
- Preskill, J. (2018). *Quantum Computing in the NISQ era and beyond.* Quantum, 2, 79. — The guiding philosophy of this repository: theoretical perfection must yield to engineering reality on current hardware.

---

## Tech Stack

| Layer | Technology |
|:---|:---|
| Quantum Simulation | Python 3.10+, IBM Qiskit, Qiskit Aer |
| Noise Modelling | `qiskit_aer.noise` — depolarising, bit-flip, measurement error models |
| Hardware Execution | IBM Quantum Cloud, Qiskit Runtime SamplerV2 |
| Data Processing | NumPy, Matplotlib |
| Visualisation Dashboard | HTML5, CSS3, Vanilla JS, GitHub Pages |
| Version Control | Git, GitHub |

---

## Installation & Usage

### 1. Clone & Environment Setup

```bash
git clone https://github.com/quantumlyquinny/NISQ-Quantum-Image-Processing.git
cd NISQ-Quantum-Image-Processing
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. IBM Quantum Credentials

Create a `.env` file in the root directory:

```
IBM_API_KEY="your_api_key_here"
IBM_CRN="your_crn_here"
```

Free IBM Quantum accounts are available at [quantum.ibm.com](https://quantum.ibm.com).

### 3. Run Local Simulations

```bash
python src/protocols/basis_encoding.py
python src/protocols/entangled_transmission.py
python src/protocols/quantum_watermarking.py
python src/protocols/amplitude_encoding.py
```

### 4. Physical QPU Execution

```bash
python src/ibm_hardware_execution.py
```

Transpiles circuits to the target backend's native gate set and submits to the least busy available QPU. Results are saved locally for comparison against simulation output.

---

## Repository Structure

```
NISQ-Quantum-Image-Processing/
├── src/
│   ├── protocols/
│   │   ├── basis_encoding.py
│   │   ├── entangled_transmission.py
│   │   ├── quantum_watermarking.py
│   │   └── amplitude_encoding.py
│   └── ibm_hardware_execution.py
├── docs/
│   └── results/
│       ├── noise_comparison.png
│       ├── qber_measurement.png
│       ├── amplitude_reconstruction.png
│       └── circuit_depth_comparison.png
├── .env.example
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Key Findings

The hardware execution results confirm the central thesis of this project:

**Shallow circuits survive NISQ hardware.** Basis encoding and quantum watermarking, both relying on single-qubit gates with minimal depth, maintained meaningful fidelity on physical hardware. The noise floor of current superconducting processors is manageable for low-depth circuits.

**Entanglement degrades predictably.** The entangled transmission protocol produced QBER measurements consistent with theoretical predictions under hardware noise — validating that Bell pair degradation can serve as a tamper-detection signal even on NISQ devices.

**Amplitude encoding is not yet practical.** The exponential compression promised by amplitude encoding collapses on real hardware. Dense CNOT compilation amplifies hardware errors beyond recovery at current noise levels, confirming that this architecture requires fault-tolerant quantum hardware to be viable.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*This project was developed as part of an independent quantum computing research initiative at Delhi Technological University.*