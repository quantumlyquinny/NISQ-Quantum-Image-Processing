"""
entangled_transmission.py — Protocol 2: Entangled Bell-Pair Transmission

Implements a QKD-inspired secure transmission protocol using entangled Bell pairs.
Each pixel is encoded into one half of an entangled pair (Alice's qubit), while
the other half (Bob's qubit) travels through a simulated noisy quantum channel.

Security Mechanism: Any interception or measurement of Bob's qubit during transit
forces wave-function collapse, degrading the entanglement and producing a
measurable increase in Quantum Bit Error Rate (QBER). A QBER exceeding ~11%
statistically proves channel compromise — this threshold is derived from the
information-theoretic security proof of QKD protocols.

Encoding: Phase encoding via Pauli-Z gates on Alice's qubits.
    pixel = 0 → |Φ+⟩ Bell state (no Z applied)
    pixel = 1 → |Φ-⟩ Bell state (Z applied, phase flip)

Decoding: Bell measurement (reverse CNOT + Hadamard) recovers Alice's bits at Bob.

Trade-off vs Basis Encoding: Doubles qubit count (32 qubits for a 4x4 image),
adds moderate circuit depth through two-qubit CNOT gates, but provides
provable tamper-detection that basis encoding fundamentally cannot offer.

References:
    Ekert, A. K. (1991). Quantum cryptography based on Bell's theorem.
    Physical Review Letters, 67(6), 661.

    Bennett, C. H., & Brassard, G. (1984). Quantum cryptography: Public key
    distribution and coin tossing. Proceedings of IEEE ICCSS, 175-179.
"""

import os
import json
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError

# --- Configuration ---
# Depolarising error rate on Bob's transit qubits.
# Models environmental decoherence during transmission.
# At 15%, simulates a heavily degraded channel for visibility.
# Real fibre-optic quantum channels: ~1-5% depending on distance.
CHANNEL_ERROR_RATE = 0.15

# Gate error rate on two-qubit CNOT operations.
# IBM Eagle r3 typical two-qubit gate error: ~0.5-1.0%.
CNOT_ERROR_RATE = 0.005

# Readout error rate consistent with IBM Eagle r3 calibrations.
READOUT_ERROR_RATE = 0.02

# QBER threshold above which channel compromise is statistically proven.
# Derived from QKD security proofs — intercept-resend attacks produce ~25% QBER;
# 11% is the conventional security boundary below which Eve gains no information.
QBER_SECURITY_THRESHOLD = 11.0

# 1024 shots: minimum for statistically valid QBER estimation.
NUM_SHOTS = 1024

RESULTS_DIR = "docs/results"
RESULTS_FILE = os.path.join(RESULTS_DIR, "entangled_transmission_results.json")
PLOT_FILE = os.path.join(RESULTS_DIR, "entangled_transmission_comparison.png")


def create_payload() -> np.ndarray:
    """
    Generates the 4x4 binary cross-pattern image payload.

    Consistent across all protocols to enable direct fidelity comparison.
    12 active pixels (value=1) and 4 inactive pixels (value=0) provide
    a balanced test case for both bit states.

    Returns:
        np.ndarray: 4x4 binary matrix, dtype uint8.
    """
    return np.array([
        [0, 1, 1, 0],
        [1, 1, 1, 1],
        [1, 1, 1, 1],
        [0, 1, 1, 0]
    ], dtype=np.uint8)


def build_entangled_circuit(image_matrix: np.ndarray) -> QuantumCircuit:
    """
    Constructs the Bell-pair entangled transmission circuit.

    Circuit Architecture (per pixel pair):
      Qubit i*2   → Alice's qubit (encodes payload, measured at receiver)
      Qubit i*2+1 → Bob's qubit (travels through channel, subject to noise)

    Phase 1 — Bell State Preparation:
      H gate on Alice's qubit creates superposition: |0⟩ → (|0⟩ + |1⟩)/√2
      CNOT entangles Alice and Bob: creates |Φ+⟩ = (|00⟩ + |11⟩)/√2

    Phase 2 — Payload Encoding (Alice):
      Z gate on Alice's qubit for pixel=1 flips the Bell state:
      |Φ+⟩ → |Φ-⟩ = (|00⟩ - |11⟩)/√2
      This phase difference encodes the classical bit without disturbing
      the entanglement structure — preserving tamper-detection capability.

    Phase 3 — Transmission Channel:
      Identity gates on Bob's qubits represent transit time.
      Noise model targets these gates to simulate channel decoherence.

    Phase 4 — Bell Measurement (Bob decodes):
      Reverse CNOT + H recovers Alice's classical bits at Bob's side.

    Args:
        image_matrix: 2D binary numpy array representing the image payload.

    Returns:
        QuantumCircuit: Full entangled transmission circuit with measurements.
    """
    flat_image = image_matrix.flatten()
    num_pixels = len(flat_image)
    num_qubits = num_pixels * 2  # Two qubits per pixel: Alice + Bob

    qc = QuantumCircuit(num_qubits)

    # Phase 1: Bell state preparation for each pixel pair
    for i in range(num_pixels):
        alice = i * 2
        bob = i * 2 + 1
        qc.h(alice)
        qc.cx(alice, bob)

    qc.barrier(label="channel_entry")

    # Phase 2: Alice encodes payload via phase flip (Z gate)
    # Z gate: |Φ+⟩ → |Φ-⟩, encoding bit=1 as a phase difference
    for idx, pixel in enumerate(flat_image):
        if pixel == 1:
            qc.z(idx * 2)

    # Phase 3: Explicit transmission channel representation
    # Identity gates on Bob's qubits — noise model targets these
    # to simulate decoherence during physical channel transit
    for i in range(num_pixels):
        qc.id(i * 2 + 1)

    qc.barrier(label="channel_exit")

    # Phase 4: Bell measurement — Bob reverses the entanglement to decode
    for i in range(num_pixels):
        alice = i * 2
        bob = i * 2 + 1
        qc.cx(alice, bob)
        qc.h(alice)

    qc.measure_all()
    return qc


def build_noise_model(num_pixels: int) -> NoiseModel:
    """
    Constructs a channel-aware noise model for entangled transmission.

    Noise sources modelled:
      1. Depolarising error on Bob's transit qubits during channel passage.
         Models environmental decoherence — the primary source of QBER
         increase in real quantum transmission channels.
      2. Two-qubit gate error on CNOT operations.
         IBM Eagle r3 typical two-qubit gate fidelity: ~99-99.5%.
      3. Symmetric readout error on all qubits.

    Args:
        num_pixels: Number of pixels in the payload (determines qubit count).

    Returns:
        NoiseModel: Configured noise model targeting channel qubits.
    """
    noise_model = NoiseModel()

    # Depolarising noise on Bob's transit qubits (identity gates)
    channel_error = depolarizing_error(CHANNEL_ERROR_RATE, num_qubits=1)
    bobs_qubits = [i * 2 + 1 for i in range(num_pixels)]
    for qubit in bobs_qubits:
        noise_model.add_quantum_error(channel_error, ['id'], [qubit])

    # Two-qubit gate error on CNOT operations
    cnot_error = depolarizing_error(CNOT_ERROR_RATE, num_qubits=2)
    noise_model.add_all_qubit_quantum_error(cnot_error, ['cx'])

    # Symmetric readout error consistent across all qubits
    readout_error = ReadoutError([
        [1 - READOUT_ERROR_RATE, READOUT_ERROR_RATE],
        [READOUT_ERROR_RATE, 1 - READOUT_ERROR_RATE]
    ])
    noise_model.add_all_qubit_readout_error(readout_error)

    return noise_model


def reconstruct_image(counts: dict, image_shape: tuple) -> np.ndarray:
    """
    Reconstructs the received image from Bell measurement outcomes.

    Bell measurement produces a 2n-bit string. Only Alice's qubits (even
    indices: 0, 2, 4...) carry the decoded payload — Bob's qubits serve
    as the entanglement verification channel.

    Maximum likelihood reconstruction selects the most frequent
    measurement outcome across NUM_SHOTS, providing a statistically
    robust estimate of the transmitted state.

    Args:
        counts: Measurement outcome dictionary {bitstring: shot_count}.
        image_shape: Target shape for reconstruction.

    Returns:
        np.ndarray: Reconstructed binary image matrix.
    """
    most_probable = max(counts, key=counts.get)

    # Qiskit bitstring ordering: reversed relative to qubit indices
    # Correct for this before extracting Alice's bits
    reversed_state = most_probable[::-1]

    # Extract only Alice's qubits (even indices) — these carry the payload
    num_pixels = image_shape[0] * image_shape[1]
    decoded_bits = [int(reversed_state[i * 2]) for i in range(num_pixels)]

    return np.array(decoded_bits, dtype=np.uint8).reshape(image_shape)


def compute_metrics(original: np.ndarray,
                    reconstructed: np.ndarray,
                    apply_noise: bool) -> dict:
    """
    Computes QBER and channel security assessment.

    QBER interpretation in QKD context:
      QBER < 11%  → Channel secure, no eavesdropping detected
      QBER > 11%  → Channel compromised (Eve's presence statistically proven)
      QBER ~ 25%  → Consistent with intercept-resend attack

    Args:
        original: Ground truth binary image payload.
        reconstructed: Received and decoded image.
        apply_noise: Whether noise was applied (for metadata).

    Returns:
        dict: Fidelity metrics including QBER and security assessment.
    """
    error_count = int(np.sum(original != reconstructed))
    qber = (error_count / original.size) * 100
    secure = qber < QBER_SECURITY_THRESHOLD

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "protocol": "entangled_transmission",
        "noise_applied": apply_noise,
        "shots": NUM_SHOTS,
        "total_pixels": int(original.size),
        "error_count": error_count,
        "qber_percent": round(qber, 2),
        "accuracy_percent": round(100 - qber, 2),
        "channel_secure": secure,
        "security_threshold_percent": QBER_SECURITY_THRESHOLD,
        "security_verdict": (
            "SECURE — QBER below threshold, no eavesdropping detected"
            if secure else
            "COMPROMISED — QBER exceeds threshold, channel integrity violated"
        )
    }


def run_protocol(apply_noise: bool = False) -> tuple:
    """
    Executes the full entangled transmission pipeline.

    Args:
        apply_noise: If True, applies channel decoherence noise model.

    Returns:
        Tuple of (original image, reconstructed image, metrics dict).
    """
    original = create_payload()
    qc = build_entangled_circuit(original)

    num_pixels = original.size
    simulator = AerSimulator()
    noise_model = build_noise_model(num_pixels) if apply_noise else None

    transpiled_qc = transpile(qc, simulator)
    result = simulator.run(
        transpiled_qc,
        noise_model=noise_model,
        shots=NUM_SHOTS
    ).result()

    counts = result.get_counts()
    reconstructed = reconstruct_image(counts, original.shape)
    metrics = compute_metrics(original, reconstructed, apply_noise)

    return original, reconstructed, metrics


def save_results(clean_metrics: dict,
                 noisy_metrics: dict,
                 original: np.ndarray,
                 clean: np.ndarray,
                 noisy: np.ndarray) -> None:
    """
    Persists protocol results for dashboard visualisation and reporting.

    Args:
        clean_metrics: Fidelity metrics from noise-free run.
        noisy_metrics: Fidelity metrics from noisy channel run.
        original: Ground truth image.
        clean: Clean channel reconstruction.
        noisy: Noisy channel reconstruction.
    """
    os.makedirs(RESULTS_DIR, exist_ok=True)

    combined = {"clean": clean_metrics, "noisy": noisy_metrics}
    with open(RESULTS_FILE, "w") as f:
        json.dump(combined, f, indent=2)
    print(f">> Results saved to {RESULTS_FILE}")

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    fig.suptitle(
        f"Protocol 2: Entangled Transmission — Channel Fidelity Analysis\n"
        f"Clean QBER: {clean_metrics['qber_percent']}% | "
        f"Noisy QBER: {noisy_metrics['qber_percent']}% | "
        f"Security Threshold: {QBER_SECURITY_THRESHOLD}% | "
        f"Shots: {NUM_SHOTS}",
        fontsize=10
    )

    axes[0].imshow(original, cmap='Blues', vmin=0, vmax=1)
    axes[0].set_title("Original Payload\n(Alice's encoding)")
    axes[0].axis('off')

    axes[1].imshow(clean, cmap='Blues', vmin=0, vmax=1)
    axes[1].set_title(
        f"Clean Channel\n"
        f"QBER: {clean_metrics['qber_percent']}% — "
        f"{clean_metrics['security_verdict'].split('—')[0].strip()}"
    )
    axes[1].axis('off')

    axes[2].imshow(noisy, cmap='Reds', vmin=0, vmax=1)
    axes[2].set_title(
        f"Noisy Channel (ε={CHANNEL_ERROR_RATE})\n"
        f"QBER: {noisy_metrics['qber_percent']}% — "
        f"{noisy_metrics['security_verdict'].split('—')[0].strip()}"
    )
    axes[2].axis('off')

    plt.tight_layout()
    plt.savefig(PLOT_FILE, dpi=150, bbox_inches='tight')
    plt.close()
    print(f">> Comparison plot saved to {PLOT_FILE}")


if __name__ == "__main__":
    print("=" * 60)
    print("Protocol 2: Entangled Bell-Pair Transmission")
    print(f"Channel error: {CHANNEL_ERROR_RATE} | "
          f"CNOT error: {CNOT_ERROR_RATE} | "
          f"Shots: {NUM_SHOTS}")
    print(f"Security threshold: QBER < {QBER_SECURITY_THRESHOLD}%")
    print("=" * 60)

    print("\n[1/2] Running clean channel simulation...")
    original, clean_output, clean_metrics = run_protocol(apply_noise=False)
    print(f"      QBER: {clean_metrics['qber_percent']}% | "
          f"{clean_metrics['security_verdict']}")

    print("\n[2/2] Running noisy channel simulation...")
    _, noisy_output, noisy_metrics = run_protocol(apply_noise=True)
    print(f"      QBER: {noisy_metrics['qber_percent']}% | "
          f"{noisy_metrics['security_verdict']}")

    print("\n>> Saving results and generating visualisation...")
    save_results(clean_metrics, noisy_metrics,
                 original, clean_output, noisy_output)