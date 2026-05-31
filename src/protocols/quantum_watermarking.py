"""
quantum_watermarking.py — Protocol 3: Quantum Watermarking via Fragile Superposition

Implements payload integrity verification using fragile superposition sentinel qubits.
Unlike the entangled transmission protocol, watermarking requires zero additional
qubits — verification overhead is embedded within the same 16-qubit register as
the payload itself.

Security Mechanism:
    Designated "sentinel" pixels are placed into superposition via Hadamard gates.
    A pristine superposition state |+⟩ = (|0⟩ + |1⟩)/√2, when measured after a
    second Hadamard, deterministically returns |0⟩. Any intervening disturbance
    (eavesdropper measurement, environmental decoherence) forces partial wave-function
    collapse — breaking the superposition and causing the sentinel to return |1⟩
    with non-zero probability.

    This is a direct application of quantum steganography: the watermark is
    physically invisible during transit but cryptographically fragile — any
    observation destroys it.

Watermark Architecture:
    - Sentinel positions: corners + inner ring (8 qubits) — high spatial coverage
    - Data positions: remaining pixels encoded via standard basis (X gate)
    - Detection: sentinel QBER > threshold triggers integrity violation alert

Trade-off vs Entangled Transmission:
    Advantage: No additional qubit overhead (16 qubits vs 32 for entanglement)
    Disadvantage: Sentinel qubits are hyper-sensitive to natural NISQ noise,
    producing false positive integrity violations even without eavesdropping.
    This false positive rate is the primary limitation of this protocol on
    current hardware.

References:
    Qu, Z., et al. (2016). A novel quantum image steganography algorithm based
    on exploiting modification direction. Quantum Information Processing, 15(6).

    Bennett, C. H., & Brassard, G. (1984). Quantum cryptography: Public key
    distribution and coin tossing. Proceedings of IEEE ICCSS, 175-179.
"""

import os
import json
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timezone
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError

# --- Configuration ---
# Depolarising error rate across all transit qubits.
# Models uniform channel decoherence during transmission.
# At 10%, simulates a moderately degraded NISQ channel.
CHANNEL_ERROR_RATE = 0.10

# Readout error rate consistent with IBM Eagle r3 calibrations (~2%).
READOUT_ERROR_RATE = 0.02

# Sentinel QBER threshold above which integrity violation is flagged.
# Below this threshold, errors are attributable to natural NISQ noise
# rather than deliberate interception.
# Set conservatively at 25% — above natural noise floor, below
# the ~50% expected from a full intercept-resend attack.
WATERMARK_QBER_THRESHOLD = 25.0

# 1024 shots for statistically valid sentinel fidelity estimation.
# Critical here: watermark detection relies on probability distributions,
# not single-shot outcomes — shots=1 would make detection meaningless.
NUM_SHOTS = 1024

RESULTS_DIR = "docs/results"
RESULTS_FILE = os.path.join(RESULTS_DIR, "quantum_watermarking_results.json")
PLOT_FILE = os.path.join(RESULTS_DIR, "quantum_watermarking_comparison.png")


def create_payload() -> np.ndarray:
    """
    Generates the 4x4 binary cross-pattern image payload.

    Consistent across all protocols to enable direct fidelity comparison.

    Returns:
        np.ndarray: 4x4 binary matrix, dtype uint8.
    """
    return np.array([
        [0, 1, 1, 0],
        [1, 1, 1, 1],
        [1, 1, 1, 1],
        [0, 1, 1, 0]
    ], dtype=np.uint8)


def create_watermark_mask() -> np.ndarray:
    """
    Defines the sentinel pixel positions for watermark embedding.

    Sentinel placement strategy: corners + inner ring provides maximum
    spatial coverage across the 4x4 grid. Sentinels are distributed
    to detect both localised and distributed channel tampering.

    Sentinel positions (1 = sentinel, 0 = data pixel):
        [1, 0, 0, 1]    ← corners
        [0, 1, 1, 0]    ← inner ring
        [0, 1, 1, 0]    ← inner ring
        [1, 0, 0, 1]    ← corners

    8 sentinel qubits, 8 data qubits — balanced verification coverage.

    Returns:
        np.ndarray: Flattened 16-element binary mask.
    """
    mask_2d = np.array([
        [1, 0, 0, 1],
        [0, 1, 1, 0],
        [0, 1, 1, 0],
        [1, 0, 0, 1]
    ], dtype=np.uint8)
    return mask_2d.flatten()


def build_watermarking_circuit(image_matrix: np.ndarray,
                               watermark_mask: np.ndarray) -> QuantumCircuit:
    """
    Constructs the quantum watermarking circuit.

    Circuit Architecture (single 16-qubit register):

    Phase 1 — Encoding (Alice):
        Sentinel qubits (mask=1): H gate → |+⟩ = (|0⟩ + |1⟩)/√2
            Superposition embeds the watermark. Pristine state is fragile —
            any measurement collapses it irreversibly.
        Data qubits (mask=0): X gate if pixel=1, else |0⟩
            Standard basis encoding for payload data.

    Phase 2 — Transmission Channel:
        Identity gates on all qubits represent transit time.
        Noise model targets these gates to simulate decoherence.

    Phase 3 — Decoding (Bob):
        Second H gate on sentinel positions reverses superposition.
        Pristine sentinels: H|+⟩ → |0⟩ (deterministic, 100% reliable)
        Disturbed sentinels: H|mixed⟩ → |1⟩ with probability p_error
        Any |1⟩ measurement on a sentinel position flags tampering.

    Args:
        image_matrix: 2D binary numpy array representing the image payload.
        watermark_mask: Flattened binary mask identifying sentinel positions.

    Returns:
        QuantumCircuit: Full watermarking circuit with measurements.
    """
    flat_image = image_matrix.flatten()
    num_pixels = len(flat_image)
    qc = QuantumCircuit(num_pixels)

    # Phase 1: Encode payload and embed watermark sentinels
    for idx in range(num_pixels):
        if watermark_mask[idx] == 1:
            # Sentinel: place into superposition — fragile to any observation
            qc.h(idx)
        else:
            # Data pixel: standard basis encoding
            if flat_image[idx] == 1:
                qc.x(idx)

    qc.barrier(label="channel_entry")

    # Phase 2: Transit channel — identity gates targeted by noise model
    for i in range(num_pixels):
        qc.id(i)

    qc.barrier(label="channel_exit")

    # Phase 3: Bob reverses Hadamard on sentinel positions
    # Pristine |+⟩ → |0⟩; disturbed superposition → |1⟩ with p_error
    for idx in range(num_pixels):
        if watermark_mask[idx] == 1:
            qc.h(idx)

    qc.measure_all()
    return qc


def build_noise_model(sentinel_qubits: list) -> NoiseModel:
    """
    Constructs a sentinel-targeted noise model for watermarking simulation.

    Noise is applied ONLY to sentinel qubits via per-qubit H gate targeting.
    This models channel decoherence disturbing the fragile superposition state
    between Alice's encoding H and Bob's decoding H.

    Physics: noise fires AFTER the encode H gate on sentinel qubits.
    Decode H then attempts to reverse a corrupted state, producing non-zero
    P(sentinel=1) proportional to the channel error rate.

    Data qubits receive NO gate noise — only readout error — ensuring
    payload QBER and sentinel QBER are independently measurable.

    Args:
        sentinel_qubits: List of qubit indices carrying watermark sentinels.

    Returns:
        NoiseModel: Sentinel-targeted noise model.
    """
    noise_model = NoiseModel()

    # Per-qubit H gate noise on sentinels only
    # Must use individual add_quantum_error calls — list API expects single qubit
    channel_error = depolarizing_error(CHANNEL_ERROR_RATE, num_qubits=1)
    for q in sentinel_qubits:
        noise_model.add_quantum_error(channel_error, ['h'], [q])

    readout_error = ReadoutError([
        [1 - READOUT_ERROR_RATE, READOUT_ERROR_RATE],
        [READOUT_ERROR_RATE, 1 - READOUT_ERROR_RATE]
    ])
    noise_model.add_all_qubit_readout_error(readout_error)
    return noise_model

def reconstruct_and_verify(counts: dict,
                           image_shape: tuple,
                           watermark_mask: np.ndarray) -> tuple:
    """
    Reconstructs the received image and evaluates watermark integrity
    using per-qubit marginal probability estimation.

    Why not MLE (most probable bitstring)?
    Under NISQ noise, a 16-qubit circuit produces hundreds of unique
    bitstrings. The most probable may appear in only ~10% of shots and
    often corresponds to the noiseless state — making MLE blind to
    distributed noise across qubits. Sentinel QBER reads 0% even when
    aggregate errors are ~25%.

    Marginal probability correctly captures distributed noise:
    For each qubit i, compute P(qubit_i = 1) across all shots.
    Sentinel QBER = mean P(sentinel_i = 1) across sentinel positions.
    Under no noise: P(sentinel = 1) ≈ 0%.
    Under channel error ε: P(sentinel = 1) ≈ ε/2 (depolarising model).

    Args:
        counts: Measurement outcome dictionary {bitstring: shot_count}.
        image_shape: Target shape for image reconstruction.
        watermark_mask: Flattened binary mask identifying sentinel positions.

    Returns:
        Tuple of (reconstructed image, sentinel QBER percent).
    """
    num_qubits = image_shape[0] * image_shape[1]
    total_shots = sum(counts.values())
    qubit_one_counts = np.zeros(num_qubits)

    for bitstring, count in counts.items():
        reversed_bs = bitstring[::-1]
        for i, bit in enumerate(reversed_bs):
            if int(bit) == 1:
                qubit_one_counts[i] += count

    # Per-qubit probability of measuring |1>
    p_one = qubit_one_counts / total_shots

    # Reconstruct: assign bit = 1 if P(|1>) > 0.5
    decoded = (p_one > 0.5).astype(np.uint8)

    # Sentinel QBER: mean P(sentinel = 1) — expected ~0% clean, rises with noise
    sentinel_indices = [i for i, m in enumerate(watermark_mask) if m == 1]
    sentinel_qber = float(np.mean(p_one[sentinel_indices]) * 100)

    return decoded.reshape(image_shape), sentinel_qber


def compute_metrics(original: np.ndarray,
                    reconstructed: np.ndarray,
                    sentinel_qber: float,
                    apply_noise: bool) -> dict:
    """
    Computes full fidelity and integrity metrics for the watermarking protocol.

    Distinguishes between two error types:
      - Payload QBER: errors in data pixel reconstruction
      - Sentinel QBER: errors in watermark integrity verification

    A channel can have low payload QBER (data arrives intact) but high
    sentinel QBER (watermark destroyed) — indicating a sophisticated
    attack that targets superposition states specifically.

    Args:
        original: Ground truth binary image payload.
        reconstructed: Received and decoded image.
        sentinel_qber: Watermark sentinel error rate.
        apply_noise: Whether noise was applied (for metadata).

    Returns:
        dict: Combined payload and watermark fidelity metrics.
    """
    # Payload metrics (data pixels only)
    watermark_mask = create_watermark_mask()
    data_indices = [i for i, m in enumerate(watermark_mask) if m == 0]
    original_data = original.flatten()[data_indices]
    reconstructed_data = reconstructed.flatten()[data_indices]

    payload_errors = int(np.sum(original_data != reconstructed_data))
    payload_qber = (payload_errors / len(data_indices)) * 100

    integrity_intact = sentinel_qber < WATERMARK_QBER_THRESHOLD

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "protocol": "quantum_watermarking",
        "noise_applied": apply_noise,
        "shots": NUM_SHOTS,
        "total_pixels": int(original.size),
        "sentinel_count": int(np.sum(watermark_mask)),
        "data_pixel_count": len(data_indices),
        "payload_error_count": payload_errors,
        "payload_qber_percent": round(payload_qber, 2),
        "sentinel_qber_percent": round(sentinel_qber, 2),
        "integrity_threshold_percent": WATERMARK_QBER_THRESHOLD,
        "integrity_intact": integrity_intact,
        "integrity_verdict": (
            "INTACT — Sentinel QBER below threshold, payload unobserved"
            if integrity_intact else
            "VIOLATED — Sentinel QBER exceeds threshold, superposition disturbed"
        )
    }


def run_protocol(apply_noise: bool = False) -> tuple:
    original = create_payload()
    watermark_mask = create_watermark_mask()
    sentinel_qubits = [i for i, m in enumerate(watermark_mask) if m == 1]
    qc = build_watermarking_circuit(original, watermark_mask)

    simulator = AerSimulator()
    # Pass sentinel_qubits to noise model — noise targets sentinels only
    noise_model = build_noise_model(sentinel_qubits) if apply_noise else None

    # optimization_level=0 is CRITICAL — prevents transpiler cancelling H+H pairs
    # The transpiler treats H+H as identity and removes both gates, which strips
    # the noise target entirely. Level 0 disables this optimisation pass.
    transpiled_qc = transpile(qc, simulator, optimization_level=0)
    result = simulator.run(
        transpiled_qc,
        noise_model=noise_model,
        shots=4096  # increased from 1024 — marginal probability needs more samples
    ).result()

    counts = result.get_counts()
    reconstructed, sentinel_qber = reconstruct_and_verify(
        counts, original.shape, watermark_mask
    )
    metrics = compute_metrics(original, reconstructed, sentinel_qber, apply_noise)
    return original, reconstructed, metrics

def save_results(clean_metrics: dict,
                 noisy_metrics: dict,
                 original: np.ndarray,
                 clean: np.ndarray,
                 noisy: np.ndarray) -> None:
    """
    Persists watermarking results for dashboard and academic reporting.

    Generates a four-panel plot showing original payload, clean reconstruction,
    noisy reconstruction, and watermark sentinel positions overlaid.

    Args:
        clean_metrics: Metrics from noise-free run.
        noisy_metrics: Metrics from noisy channel run.
        original: Ground truth image.
        clean: Clean channel reconstruction.
        noisy: Noisy channel reconstruction.
    """
    os.makedirs(RESULTS_DIR, exist_ok=True)

    combined = {"clean": clean_metrics, "noisy": noisy_metrics}
    with open(RESULTS_FILE, "w") as f:
        json.dump(combined, f, indent=2)
    print(f">> Results saved to {RESULTS_FILE}")

    # Sentinel position visualisation overlay
    watermark_mask = create_watermark_mask().reshape(original.shape)

    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    fig.suptitle(
        f"Protocol 3: Quantum Watermarking — Integrity Analysis\n"
        f"Clean Sentinel QBER: {clean_metrics['sentinel_qber_percent']}% | "
        f"Noisy Sentinel QBER: {noisy_metrics['sentinel_qber_percent']}% | "
        f"Threshold: {WATERMARK_QBER_THRESHOLD}% | Shots: {NUM_SHOTS}",
        fontsize=10
    )

    axes[0].imshow(original, cmap='Blues', vmin=0, vmax=1)
    axes[0].set_title("Original Payload")
    axes[0].axis('off')

    axes[1].imshow(watermark_mask, cmap='Oranges', vmin=0, vmax=1)
    axes[1].set_title("Sentinel Positions\n(8 of 16 qubits)")
    axes[1].axis('off')

    axes[2].imshow(clean, cmap='Blues', vmin=0, vmax=1)
    axes[2].set_title(
        f"Clean Channel\n"
        f"Sentinel QBER: {clean_metrics['sentinel_qber_percent']}% — "
        f"{clean_metrics['integrity_verdict'].split('—')[0].strip()}"
    )
    axes[2].axis('off')

    axes[3].imshow(noisy, cmap='Reds', vmin=0, vmax=1)
    axes[3].set_title(
        f"Noisy Channel (ε={CHANNEL_ERROR_RATE})\n"
        f"Sentinel QBER: {noisy_metrics['sentinel_qber_percent']}% — "
        f"{noisy_metrics['integrity_verdict'].split('—')[0].strip()}"
    )
    axes[3].axis('off')

    plt.tight_layout()
    plt.savefig(PLOT_FILE, dpi=150, bbox_inches='tight')
    plt.close()
    print(f">> Comparison plot saved to {PLOT_FILE}")


if __name__ == "__main__":
    print("=" * 60)
    print("Protocol 3: Quantum Watermarking — Integrity Verification")
    print(f"Channel error: {CHANNEL_ERROR_RATE} | "
          f"Readout error: {READOUT_ERROR_RATE} | "
          f"Shots: {NUM_SHOTS}")
    print(f"Sentinel threshold: QBER < {WATERMARK_QBER_THRESHOLD}%")
    print("=" * 60)

    print("\n[1/2] Running clean channel simulation...")
    original, clean_output, clean_metrics = run_protocol(apply_noise=False)
    print(f"      Payload QBER: {clean_metrics['payload_qber_percent']}% | "
          f"Sentinel QBER: {clean_metrics['sentinel_qber_percent']}%")
    print(f"      Verdict: {clean_metrics['integrity_verdict']}")

    print("\n[2/2] Running noisy channel simulation...")
    _, noisy_output, noisy_metrics = run_protocol(apply_noise=True)
    print(f"      Payload QBER: {noisy_metrics['payload_qber_percent']}% | "
          f"Sentinel QBER: {noisy_metrics['sentinel_qber_percent']}%")
    print(f"      Verdict: {noisy_metrics['integrity_verdict']}")

    print("\n>> Saving results and generating visualisation...")
    save_results(clean_metrics, noisy_metrics,
                 original, clean_output, noisy_output)