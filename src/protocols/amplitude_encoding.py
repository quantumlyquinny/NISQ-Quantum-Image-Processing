"""
amplitude_encoding.py — Protocol 4: Amplitude Encoding (Efficiency Route)

Implements exponential spatial compression by mapping classical pixel values
directly onto qubit probability amplitudes. A 16-pixel image compresses into
4 qubits — a log2(N) reduction impossible in classical systems.

Compression Mechanism:
    Classical pixel values are L2-normalised to satisfy the Born rule constraint:
    sum(|amplitude_i|^2) = 1.0 (total probability must equal 1).
    Each pixel maps to a computational basis state |i⟩ with probability amplitude
    sqrt(pixel_i / sum_of_pixels). The pixel value is recovered by measuring which
    basis state |i⟩ the system collapses to.

Why This Protocol Fails on NISQ Hardware:
    The compression comes at a severe cost. Arbitrary quantum state preparation
    (the Möttönen decomposition, as used here) compiles into a dense network of
    single-qubit U gates and two-qubit CNOT gates. For a 4-qubit system, this
    produces circuit depth ~16 with 8 CNOT gates.

    On NISQ hardware, each CNOT gate carries ~0.5-2% error. Eight chained
    CNOT gates accumulate errors multiplicatively — the state degrades before
    it can even be transmitted. This is precisely what Preskill (2018) describes
    as the fundamental bottleneck of the NISQ era: deep circuits die from noise.

    Basis encoding (Protocol 1) uses only 1-gate circuits and survives NISQ
    hardware. Amplitude encoding uses 16-gate circuits and does not.

Noise Model:
    Unlike basis/watermarking protocols which target single-qubit gates, amplitude
    encoding noise must target the two-qubit CNOT gates (cx) and single-qubit
    rotations (u) that the StatePreparation gate actually compiles into.
    This accurately models NISQ hardware gate error accumulation.

References:
    Le, P. Q., et al. (2011). A flexible representation of quantum images for
    polynomial preparation, image compression, and processing operations.
    Quantum Information Processing, 10(1), 63-84.

    Möttönen, M., et al. (2004). Decomposition of arbitrary unitary matrices.
    Physical Review Letters, 93(13), 130502.
    (Explains the CNOT scaling that makes amplitude encoding NISQ-fragile.)

    Preskill, J. (2018). Quantum Computing in the NISQ era and beyond.
    Quantum, 2, 79. https://doi.org/10.22331/q-2018-08-06-79
"""

import os
import json
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timezone
from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import StatePreparation
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError

# --- Configuration ---
# Two-qubit CNOT gate error rate.
# IBM Eagle r3 typical cx gate fidelity: ~99.0-99.5% (error: 0.5-1.0%).
# We use 5% to simulate a degraded NISQ channel — at IBM's actual error rates
# the protocol still degrades measurably but requires more shots to observe.
CX_GATE_ERROR_RATE = 0.05

# Single-qubit rotation gate error rate.
# Typically ~4x lower than two-qubit gate error on IBM hardware.
U_GATE_ERROR_RATE = 0.0125

# Readout error rate consistent with IBM Eagle r3 calibrations (~2%).
READOUT_ERROR_RATE = 0.02

# Probability threshold for pixel reconstruction.
# Active pixels each carry ~1/num_active_pixels probability.
# For our 12-active-pixel image: ~8.3% per pixel.
# Threshold set at 0.5/num_pixels = ~3.1% to distinguish signal from noise floor.
RECONSTRUCTION_THRESHOLD_FACTOR = 0.5

# 8192 shots required: amplitude encoding produces 16 possible outcomes
# with ~8% probability each. At lower shot counts, low-probability pixels
# are missed entirely. 8192 ensures all active pixels are sampled reliably.
NUM_SHOTS = 8192

RESULTS_DIR = "docs/results"
RESULTS_FILE = os.path.join(RESULTS_DIR, "amplitude_encoding_results.json")
PLOT_FILE = os.path.join(RESULTS_DIR, "amplitude_encoding_comparison.png")


def create_payload() -> np.ndarray:
    """
    Generates the 4x4 binary cross-pattern image payload.

    Consistent across all protocols to enable direct fidelity comparison.
    12 active pixels (value=1) produce amplitude ~0.289 each (1/sqrt(12)).
    4 inactive pixels (value=0) produce zero amplitude — they collapse the
    state space from 16 to 12 active basis states.

    Returns:
        np.ndarray: 4x4 binary matrix, dtype float64.
    """
    return np.array([
        [0, 1, 1, 0],
        [1, 1, 1, 1],
        [1, 1, 1, 1],
        [0, 1, 1, 0]
    ], dtype=np.float64)


def normalise_amplitudes(image_matrix: np.ndarray) -> np.ndarray:
    """
    Normalises pixel values to valid quantum probability amplitudes.

    Quantum mechanics requires: sum(|amplitude_i|^2) = 1.0 (Born rule).
    L2 normalisation satisfies this constraint:
        amplitude_i = pixel_i / ||pixel_vector||_2

    For our binary image, each active pixel gets amplitude 1/sqrt(12) ≈ 0.289,
    and each inactive pixel gets amplitude 0. Measurement probability for
    active pixel i: |amplitude_i|^2 = 1/12 ≈ 8.3%.

    Args:
        image_matrix: 2D pixel array (values need not be binary).

    Returns:
        np.ndarray: Flattened L2-normalised amplitude vector.

    Raises:
        ValueError: If image is all zeros (undefined normalisation).
    """
    flat = image_matrix.flatten().astype(np.float64)
    norm_factor = np.linalg.norm(flat)
    if norm_factor == 0:
        raise ValueError("Cannot normalise a zero image — no amplitude to encode.")
    return flat / norm_factor


def build_amplitude_circuit(normalised_amplitudes: np.ndarray) -> tuple:
    """
    Constructs the amplitude encoding circuit using Möttönen state preparation.

    The StatePreparation gate decomposes arbitrary amplitude vectors into
    sequences of U gates (single-qubit rotations) and CX gates (two-qubit
    entangling operations). For 4 qubits, this produces:
        - ~12 U gates
        - ~8 CX gates
        - Circuit depth ~16

    This is the Möttönen decomposition (Phys. Rev. Lett. 93, 130502, 2004).
    The depth scales as O(2^n) for n qubits — making amplitude encoding
    exponentially more expensive to prepare as image size grows.

    Transpilation targets ['cx', 'u', 'measure', 'reset'] to force full
    decomposition into real hardware basis gates, making the circuit depth
    and CNOT count visible and measurable.

    Args:
        normalised_amplitudes: L2-normalised amplitude vector of length 2^n.

    Returns:
        Tuple of (QuantumCircuit, transpiled QuantumCircuit, gate_stats dict).
    """
    num_qubits = int(np.log2(len(normalised_amplitudes)))

    qc = QuantumCircuit(num_qubits)
    qc.append(StatePreparation(normalised_amplitudes), range(num_qubits))
    qc.measure_all()

    simulator = AerSimulator()
    transpiled_qc = transpile(
        qc,
        simulator,
        optimization_level=1,
        basis_gates=['cx', 'u', 'measure', 'reset']
    )

    gate_stats = {
        "cx_count": transpiled_qc.count_ops().get('cx', 0),
        "u_count": transpiled_qc.count_ops().get('u', 0),
        "circuit_depth": transpiled_qc.depth(),
        "total_gates": sum(transpiled_qc.count_ops().values()),
    }

    return qc, transpiled_qc, gate_stats


def build_noise_model() -> NoiseModel:
    """
    Constructs a gate-accurate noise model for amplitude encoding simulation.

    Amplitude encoding noise must target the gates StatePreparation actually
    compiles into — CX and U gates. Targeting identity gates (as in naive
    implementations) has no effect because the transpiler strips them.

    The dominant noise source is CX gate error: 8 chained CX gates at 5%
    error each produce cumulative degradation of ~(1-0.05)^8 ≈ 66% fidelity
    before any measurement. This is the core NISQ fragility demonstrated here.

    Returns:
        NoiseModel: Gate-accurate noise model targeting cx and u gates.
    """
    noise_model = NoiseModel()

    # Two-qubit CX gate depolarising error — dominant NISQ noise source
    # for amplitude encoding due to deep CNOT network
    cx_error = depolarizing_error(CX_GATE_ERROR_RATE, num_qubits=2)
    noise_model.add_all_qubit_quantum_error(cx_error, ['cx'])

    # Single-qubit U gate depolarising error
    u_error = depolarizing_error(U_GATE_ERROR_RATE, num_qubits=1)
    noise_model.add_all_qubit_quantum_error(u_error, ['u'])

    # Readout error consistent with IBM Eagle r3 calibrations
    readout_error = ReadoutError([
        [1 - READOUT_ERROR_RATE, READOUT_ERROR_RATE],
        [READOUT_ERROR_RATE, 1 - READOUT_ERROR_RATE]
    ])
    noise_model.add_all_qubit_readout_error(readout_error)

    return noise_model


def reconstruct_image(counts: dict,
                      num_pixels: int,
                      image_shape: tuple) -> tuple:
    """
    Reconstructs the image from measurement probability distribution.

    Amplitude encoding does not use MLE or marginal probability — it uses
    probability thresholding. Each measurement outcome |i⟩ maps to pixel i.
    The probability of outcome |i⟩ is proportional to pixel_i^2.

    Threshold logic:
        probability > threshold → pixel = 1 (active)
        probability ≤ threshold → pixel = 0 (inactive)

    Threshold = RECONSTRUCTION_THRESHOLD_FACTOR / num_pixels.
    For our 16-pixel image: threshold = 0.5/16 = 3.125%.
    Active pixels contribute ~8.3% — well above threshold under clean conditions.
    Under noise, active pixels leak probability to inactive pixel indices,
    causing misclassification when leaked probability exceeds threshold.

    Args:
        counts: Measurement outcome dictionary {bitstring: shot_count}.
        num_pixels: Total number of pixels (= 2^num_qubits).
        image_shape: Target shape for reconstruction.

    Returns:
        Tuple of (reconstructed image, probability distribution array).
    """
    total_shots = sum(counts.values())
    threshold = RECONSTRUCTION_THRESHOLD_FACTOR / num_pixels

    pixel_probabilities = np.zeros(num_pixels)
    for bitstring, count in counts.items():
        # Qiskit bitstring ordering: reversed relative to qubit indices
        pixel_index = int(bitstring[::-1], 2)
        pixel_probabilities[pixel_index] = count / total_shots

    reconstructed = (pixel_probabilities > threshold).astype(np.uint8)
    return reconstructed.reshape(image_shape), pixel_probabilities


def compute_metrics(original: np.ndarray,
                    reconstructed: np.ndarray,
                    gate_stats: dict,
                    apply_noise: bool) -> dict:
    """
    Computes reconstruction fidelity and circuit complexity metrics.

    Circuit complexity metrics are central to amplitude encoding analysis —
    they explain WHY the protocol degrades under noise (deep circuit) while
    basis encoding survives (shallow circuit).

    Args:
        original: Ground truth binary image payload.
        reconstructed: Probability-threshold reconstructed image.
        gate_stats: Circuit gate counts and depth from build_amplitude_circuit().
        apply_noise: Whether noise was applied (for metadata).

    Returns:
        dict: Fidelity and circuit complexity metrics.
    """
    original_binary = (original > 0).astype(np.uint8)
    error_count = int(np.sum(reconstructed != original_binary))
    qber = (error_count / original.size) * 100

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "protocol": "amplitude_encoding",
        "noise_applied": apply_noise,
        "shots": NUM_SHOTS,
        "total_pixels": int(original.size),
        "error_count": error_count,
        "qber_percent": round(qber, 2),
        "accuracy_percent": round(100 - qber, 2),
        "circuit_depth": gate_stats["circuit_depth"],
        "cx_gate_count": gate_stats["cx_count"],
        "u_gate_count": gate_stats["u_count"],
        "total_gates": gate_stats["total_gates"],
        "nisq_verdict": (
            "DEGRADED — Deep CNOT network exceeds NISQ noise tolerance"
            if qber > 0 else
            "INTACT — Clean simulation (noise-free baseline)"
        )
    }


def run_protocol(apply_noise: bool = False) -> tuple:
    """
    Executes the full amplitude encoding pipeline.

    Args:
        apply_noise: If True, applies CX/U gate error noise model.

    Returns:
        Tuple of (original image, reconstructed image, metrics dict,
                  probability distribution array).
    """
    original = create_payload()
    normalised_amplitudes = normalise_amplitudes(original)
    qc, transpiled_qc, gate_stats = build_amplitude_circuit(normalised_amplitudes)

    simulator = AerSimulator()
    noise_model = build_noise_model() if apply_noise else None

    result = simulator.run(
        transpiled_qc,
        noise_model=noise_model,
        shots=NUM_SHOTS
    ).result()

    counts = result.get_counts()
    num_pixels = original.size
    reconstructed, probabilities = reconstruct_image(counts, num_pixels, original.shape)
    metrics = compute_metrics(original, reconstructed, gate_stats, apply_noise)

    return original, reconstructed, metrics, probabilities


def save_results(clean_metrics: dict,
                 noisy_metrics: dict,
                 original: np.ndarray,
                 clean: np.ndarray,
                 noisy: np.ndarray,
                 clean_probs: np.ndarray,
                 noisy_probs: np.ndarray) -> None:
    """
    Persists amplitude encoding results for dashboard and academic reporting.

    Generates a five-panel plot: original, clean reconstruction, noisy
    reconstruction, clean probability distribution, noisy probability
    distribution. The probability plots are the key visualisation for
    amplitude encoding — they show exactly how noise redistributes
    probability mass from active to inactive pixel indices.

    Args:
        clean_metrics: Metrics from noise-free run.
        noisy_metrics: Metrics from noisy run.
        original: Ground truth image.
        clean: Clean reconstruction.
        noisy: Noisy reconstruction.
        clean_probs: Clean probability distribution over pixel indices.
        noisy_probs: Noisy probability distribution over pixel indices.
    """
    os.makedirs(RESULTS_DIR, exist_ok=True)

    combined = {"clean": clean_metrics, "noisy": noisy_metrics}
    with open(RESULTS_FILE, "w") as f:
        json.dump(combined, f, indent=2)
    print(f">> Results saved to {RESULTS_FILE}")

    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    fig.suptitle(
        f"Protocol 4: Amplitude Encoding — NISQ Fragility Analysis\n"
        f"Circuit depth: {clean_metrics['circuit_depth']} | "
        f"CX gates: {clean_metrics['cx_gate_count']} | "
        f"Clean QBER: {clean_metrics['qber_percent']}% | "
        f"Noisy QBER: {noisy_metrics['qber_percent']}% | "
        f"Shots: {NUM_SHOTS}",
        fontsize=10
    )

    # Row 1: Image reconstructions
    axes[0, 0].imshow(original, cmap='Blues', vmin=0, vmax=1)
    axes[0, 0].set_title("Original Payload\n(12 active pixels)")
    axes[0, 0].axis('off')

    axes[0, 1].imshow(clean, cmap='Blues', vmin=0, vmax=1)
    axes[0, 1].set_title(
        f"Clean Simulation\nQBER: {clean_metrics['qber_percent']}%"
    )
    axes[0, 1].axis('off')

    axes[0, 2].imshow(noisy, cmap='Reds', vmin=0, vmax=1)
    axes[0, 2].set_title(
        f"Noisy Simulation (CX ε={CX_GATE_ERROR_RATE})\n"
        f"QBER: {noisy_metrics['qber_percent']}% — "
        f"{noisy_metrics['nisq_verdict'].split('—')[0].strip()}"
    )
    axes[0, 2].axis('off')

    # Row 2: Probability distributions — key visualisation for amplitude encoding
    pixel_indices = np.arange(original.size)
    active_pixels = np.where(original.flatten() > 0)[0]
    threshold = RECONSTRUCTION_THRESHOLD_FACTOR / original.size

    axes[1, 0].bar(pixel_indices, clean_probs,
                   color=['steelblue' if i in active_pixels else 'lightgrey'
                          for i in pixel_indices])
    axes[1, 0].axhline(y=threshold, color='red', linestyle='--',
                       linewidth=1, label=f'Threshold ({threshold:.3f})')
    axes[1, 0].set_title("Clean Probability Distribution\n"
                          "(active pixels above threshold)")
    axes[1, 0].set_xlabel("Pixel Index")
    axes[1, 0].set_ylabel("Measurement Probability")
    axes[1, 0].legend(fontsize=8)

    axes[1, 1].bar(pixel_indices, noisy_probs,
                   color=['salmon' if i in active_pixels else 'lightcoral'
                          for i in pixel_indices])
    axes[1, 1].axhline(y=threshold, color='red', linestyle='--',
                       linewidth=1, label=f'Threshold ({threshold:.3f})')
    axes[1, 1].set_title("Noisy Probability Distribution\n"
                          "(noise redistributes probability mass)")
    axes[1, 1].set_xlabel("Pixel Index")
    axes[1, 1].set_ylabel("Measurement Probability")
    axes[1, 1].legend(fontsize=8)

    # Difference plot: shows exactly where noise causes misclassification
    prob_diff = noisy_probs - clean_probs
    colors = ['red' if d < 0 else 'green' for d in prob_diff]
    axes[1, 2].bar(pixel_indices, prob_diff, color=colors, alpha=0.7)
    axes[1, 2].axhline(y=0, color='black', linewidth=0.5)
    axes[1, 2].set_title("Probability Shift (Noisy − Clean)\n"
                          "(red = lost probability, green = noise leakage)")
    axes[1, 2].set_xlabel("Pixel Index")
    axes[1, 2].set_ylabel("Probability Δ")

    plt.tight_layout()
    plt.savefig(PLOT_FILE, dpi=150, bbox_inches='tight')
    plt.close()
    print(f">> Comparison plot saved to {PLOT_FILE}")


if __name__ == "__main__":
    print("=" * 60)
    print("Protocol 4: Amplitude Encoding — NISQ Fragility Analysis")
    print(f"CX error: {CX_GATE_ERROR_RATE} | "
          f"U error: {U_GATE_ERROR_RATE} | "
          f"Shots: {NUM_SHOTS}")
    print("=" * 60)

    print("\n[1/2] Running clean simulation (no noise)...")
    original, clean_output, clean_metrics, clean_probs = run_protocol(
        apply_noise=False)
    print(f"      Circuit depth: {clean_metrics['circuit_depth']} | "
          f"CX gates: {clean_metrics['cx_gate_count']}")
    print(f"      QBER: {clean_metrics['qber_percent']}% | "
          f"{clean_metrics['nisq_verdict']}")

    print("\n[2/2] Running noisy simulation...")
    _, noisy_output, noisy_metrics, noisy_probs = run_protocol(apply_noise=True)
    print(f"      QBER: {noisy_metrics['qber_percent']}% | "
          f"{noisy_metrics['nisq_verdict']}")

    print(f"\n>> Circuit complexity vs Protocol 1 (Basis Encoding):")
    print(f"   Basis Encoding depth:    ~1  | CX gates: 0")
    print(f"   Amplitude Encoding depth: {clean_metrics['circuit_depth']:2d} | "
          f"CX gates: {clean_metrics['cx_gate_count']}")
    print(f"   This {clean_metrics['circuit_depth']}x depth increase is why "
          f"amplitude encoding fails on NISQ hardware.")

    print("\n>> Saving results and generating visualisation...")
    save_results(clean_metrics, noisy_metrics,
                 original, clean_output, noisy_output,
                 clean_probs, noisy_probs)
