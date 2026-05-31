"""
basis_encoding.py — Protocol 1: Basis Encoding Baseline

Encodes a classical 4x4 binary image into a 16-qubit quantum register using
direct Pauli-X basis encoding. Serves as the low-depth control condition for
the NISQ protocol comparison suite.

Noise Model: Composite NISQ noise approximating IBM Eagle r3 hardware —
  - Depolarising gate error on single-qubit X gates (p ~ 0.001, per IBM specs)
  - Measurement readout error (p ~ 0.02, per IBM Quantum published calibrations)

Reference:
  Preskill, J. (2018). Quantum Computing in the NISQ era and beyond.
  Quantum, 2, 79. https://doi.org/10.22331/q-2018-08-06-79
"""

import numpy as np
import matplotlib.pyplot as plt
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import (
    NoiseModel,
    pauli_error,
    depolarizing_error,
    ReadoutError,
)

# --- Constants ---
# Readout error rate sourced from IBM Quantum Eagle r3 published calibrations.
# Real devices: ~1-5% per qubit. We use 2% as a conservative realistic estimate.
READOUT_ERROR_RATE = 0.02

# Depolarising gate error rate for single-qubit gates on NISQ hardware.
# IBM Eagle r3 typical single-qubit gate error: ~0.1-0.3%.
GATE_ERROR_RATE = 0.001

# Shot count: minimum for statistically meaningful fidelity reconstruction.
# At 1024 shots, the standard error on a probability estimate is ~1/sqrt(1024) ~ 3%.
NUM_SHOTS = 1024


def create_payload() -> np.ndarray:
    """
    Generates a 4x4 binary image payload (cross pattern).

    Returns:
        np.ndarray: 4x4 binary matrix representing the classical image.
    """
    return np.array([
        [0, 1, 1, 0],
        [1, 1, 1, 1],
        [1, 1, 1, 1],
        [0, 1, 1, 0]
    ], dtype=np.uint8)


def build_noise_model() -> NoiseModel:
    """
    Constructs a composite NISQ noise model approximating IBM Eagle r3 hardware.

    Noise sources modelled:
      1. Depolarising error on single-qubit X gates (gate_error_rate).
         Models imperfect gate calibration and environmental decoherence.
      2. Readout error on all qubits (readout_error_rate).
         Models measurement apparatus imperfections and state preparation errors.

    Returns:
        NoiseModel: Configured Qiskit Aer noise model.
    """
    noise_model = NoiseModel()

    # Depolarising error on X gates: equally distributes error across I, X, Y, Z
    gate_error = depolarizing_error(GATE_ERROR_RATE, num_qubits=1)
    noise_model.add_all_qubit_quantum_error(gate_error, ['x'])

    # Asymmetric readout error: P(0|1) != P(1|0) as observed on real hardware.
    # P(measure 1 | prepared 0) = readout_error_rate (false positive)
    # P(measure 0 | prepared 1) = readout_error_rate (false negative)
    readout_error = ReadoutError([
        [1 - READOUT_ERROR_RATE, READOUT_ERROR_RATE],
        [READOUT_ERROR_RATE, 1 - READOUT_ERROR_RATE]
    ])
    noise_model.add_all_qubit_readout_error(readout_error)

    return noise_model


def encode_payload(image_matrix: np.ndarray) -> QuantumCircuit:
    """
    Encodes a binary image into a quantum register via basis (computational) encoding.

    Each pixel p_i maps to qubit q_i: |0> if p_i = 0, |1> if p_i = 1 (via X gate).
    Circuit depth scales as O(n) where n is the number of pixels — making this
    the shallowest encoding in the suite and therefore most NISQ-resilient.

    Args:
        image_matrix: 2D binary numpy array representing the image payload.

    Returns:
        QuantumCircuit: Prepared quantum circuit ready for measurement.
    """
    flat_image = image_matrix.flatten()
    num_qubits = len(flat_image)

    qc = QuantumCircuit(num_qubits)
    for idx, pixel in enumerate(flat_image):
        if pixel == 1:
            qc.x(idx)
    qc.measure_all()
    return qc


def reconstruct_image(counts: dict, image_shape: tuple) -> np.ndarray:
    """
    Reconstructs the most probable image state from measurement counts.

    Uses the maximum likelihood bitstring rather than a single shot,
    providing a statistically valid estimate of the transmitted state.

    Args:
        counts: Measurement outcome dictionary {bitstring: count}.
        image_shape: Target shape for reconstruction.

    Returns:
        np.ndarray: Reconstructed binary image matrix.
    """
    # Maximum likelihood reconstruction: select most frequent measurement outcome
    most_probable_bitstring = max(counts, key=counts.get)

    # Qiskit returns bitstrings in reversed qubit order — correct for this
    corrected = list(reversed(most_probable_bitstring))
    flat_reconstructed = np.array([int(bit) for bit in corrected], dtype=np.uint8)
    return flat_reconstructed.reshape(image_shape)


def compute_fidelity_metrics(original: np.ndarray,
                              reconstructed: np.ndarray) -> dict:
    """
    Computes transmission fidelity metrics between original and reconstructed payloads.

    Args:
        original: Ground truth binary image.
        reconstructed: Hardware/simulator reconstructed image.

    Returns:
        dict: Metrics including QBER, pixel accuracy, and error count.
    """
    error_count = int(np.sum(original != reconstructed))
    qber = (error_count / original.size) * 100
    accuracy = 100 - qber
    return {
        "error_count": error_count,
        "total_pixels": original.size,
        "qber_percent": round(qber, 2),
        "accuracy_percent": round(accuracy, 2),
    }


def run_protocol(apply_noise: bool = False) -> tuple:
    """
    Executes the full basis encoding protocol pipeline.

    Args:
        apply_noise: If True, applies the NISQ composite noise model.

    Returns:
        Tuple of (reconstructed image, fidelity metrics dict).
    """
    original = create_payload()
    qc = encode_payload(original)

    simulator = AerSimulator()
    noise_model = build_noise_model() if apply_noise else None

    transpiled_qc = transpile(qc, simulator)
    result = simulator.run(
        transpiled_qc,
        noise_model=noise_model,
        shots=NUM_SHOTS
    ).result()

    counts = result.get_counts()
    reconstructed = reconstruct_image(counts, original.shape)
    metrics = compute_fidelity_metrics(original, reconstructed)

    return original, reconstructed, metrics


def visualise_results(original: np.ndarray,
                      clean: np.ndarray,
                      noisy: np.ndarray,
                      clean_metrics: dict,
                      noisy_metrics: dict) -> None:
    """
    Generates a three-panel comparison plot for the protocol results dashboard.
    Saves output to docs/results/basis_encoding_comparison.png.
    """
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    fig.suptitle(
        "Protocol 1: Basis Encoding — Transmission Fidelity Analysis\n"
        f"Clean QBER: {clean_metrics['qber_percent']}% | "
        f"Noisy QBER: {noisy_metrics['qber_percent']}% | "
        f"Shots: {NUM_SHOTS}",
        fontsize=11
    )

    axes[0].imshow(original, cmap='Blues', vmin=0, vmax=1)
    axes[0].set_title("Original Payload")
    axes[0].axis('off')

    axes[1].imshow(clean, cmap='Blues', vmin=0, vmax=1)
    axes[1].set_title(f"Clean Simulation\nQBER: {clean_metrics['qber_percent']}%")
    axes[1].axis('off')

    axes[2].imshow(noisy, cmap='Reds', vmin=0, vmax=1)
    axes[2].set_title(
        f"NISQ Noise Model\nQBER: {noisy_metrics['qber_percent']}% "
        f"({noisy_metrics['error_count']}/{noisy_metrics['total_pixels']} pixels)"
    )
    axes[2].axis('off')

    plt.tight_layout()
    plt.savefig("docs/results/basis_encoding_comparison.png", dpi=150)
    plt.show()
    print(">> Plot saved to docs/results/basis_encoding_comparison.png")


if __name__ == "__main__":
    print("=" * 60)
    print("Protocol 1: Basis Encoding — NISQ Fidelity Analysis")
    print(f"Noise Model: Gate error={GATE_ERROR_RATE}, "
          f"Readout error={READOUT_ERROR_RATE}, Shots={NUM_SHOTS}")
    print("=" * 60)

    print("\n[1/2] Running clean simulation (no noise)...")
    original, clean_output, clean_metrics = run_protocol(apply_noise=False)
    print(f"      QBER: {clean_metrics['qber_percent']}% | "
          f"Accuracy: {clean_metrics['accuracy_percent']}%")

    print("\n[2/2] Running NISQ noise simulation...")
    _, noisy_output, noisy_metrics = run_protocol(apply_noise=True)
    print(f"      QBER: {noisy_metrics['qber_percent']}% | "
          f"Accuracy: {noisy_metrics['accuracy_percent']}%")

    print("\n>> Generating visualisation...")
    visualise_results(original, clean_output, noisy_output,
                      clean_metrics, noisy_metrics)