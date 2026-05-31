"""
ibm_hardware_execution.py — Physical QPU Execution via Qiskit Runtime SamplerV2

Executes the basis encoding protocol on real IBM superconducting quantum hardware,
bypassing local simulation entirely. Uses Qiskit Runtime Primitives (SamplerV2)
for modern job submission and result retrieval.

Hardware Target: Least busy operational IBM QPU (e.g., Eagle r3 architecture).
Credentials: Loaded from .env file — never hardcoded.

Key distinction from simulation: results reflect authentic hardware noise sources
including T1/T2 decoherence, gate calibration drift, crosstalk between physical
qubits, and measurement apparatus imperfections — none of which are fully
captured by classical noise models.

Reference:
    Preskill, J. (2018). Quantum Computing in the NISQ era and beyond.
    Quantum, 2, 79. https://doi.org/10.22331/q-2018-08-06-79
"""

import os
import json
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from dotenv import load_dotenv
from qiskit import QuantumCircuit, transpile
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

# --- Configuration ---
# 1024 shots: minimum for statistically valid fidelity reconstruction.
# Standard error on probability estimate: ~1/sqrt(1024) ~ 3%.
# shots=1 produces a single random sample — not a meaningful fidelity metric.
NUM_SHOTS = 1024

RESULTS_DIR = "docs/results"
RESULTS_FILE = os.path.join(RESULTS_DIR, "hardware_execution_results.json")
PLOT_FILE = os.path.join(RESULTS_DIR, "hardware_qber_comparison.png")


def load_credentials() -> tuple[str, str]:
    """
    Loads IBM Quantum credentials from environment variables.

    Credentials are stored in a .env file and never hardcoded.
    See .env.example for required variable names.

    Returns:
        Tuple of (api_key, crn_instance).

    Raises:
        EnvironmentError: If required credentials are missing.
    """
    load_dotenv()
    api_key = os.getenv("IBM_API_KEY")
    crn = os.getenv("IBM_CRN")

    if not api_key or not crn:
        raise EnvironmentError(
            "Missing IBM Quantum credentials. "
            "Ensure IBM_API_KEY and IBM_CRN are set in your .env file. "
            "See .env.example for reference."
        )
    return api_key, crn


def create_payload() -> np.ndarray:
    """
    Generates the 4x4 binary cross-pattern image payload.

    This specific pattern (12 active pixels, 4 inactive) provides a
    balanced test case — neither all-zeros nor all-ones — ensuring
    meaningful fidelity measurement across both bit states.

    Returns:
        np.ndarray: 4x4 binary matrix, dtype uint8.
    """
    return np.array([
        [0, 1, 1, 0],
        [1, 1, 1, 1],
        [1, 1, 1, 1],
        [0, 1, 1, 0]
    ], dtype=np.uint8)


def build_circuit(image_matrix: np.ndarray) -> QuantumCircuit:
    """
    Encodes a binary image into a quantum register via computational basis encoding.

    Encoding scheme: pixel p_i maps to qubit q_i.
        p_i = 0 → |0⟩ (no gate applied, default qubit state)
        p_i = 1 → |1⟩ (Pauli-X gate applied)

    Circuit depth is O(n) where n = number of pixels, using only single-qubit
    X gates. This shallow depth makes basis encoding the most NISQ-resilient
    protocol in the suite — minimal gate error accumulation before measurement.

    Args:
        image_matrix: 2D binary numpy array representing the image payload.

    Returns:
        QuantumCircuit: Prepared circuit with measurement operations appended.
    """
    flat_image = image_matrix.flatten()
    num_qubits = len(flat_image)

    qc = QuantumCircuit(num_qubits)
    for idx, pixel in enumerate(flat_image):
        if pixel == 1:
            qc.x(idx)
    qc.measure_all()
    return qc


def connect_to_backend(api_key: str, crn: str):
    """
    Authenticates with IBM Quantum Cloud and selects the optimal QPU.

    Backend selection uses least_busy() to minimise queue wait time.
    Filters for operational=True and simulator=False to ensure
    physical hardware execution only.

    Args:
        api_key: IBM Quantum API key.
        crn: IBM Cloud Resource Name identifying the quantum instance.

    Returns:
        IBMBackend: Selected physical quantum backend.
    """
    print(">> Authenticating with IBM Quantum Cloud...")
    service = QiskitRuntimeService(
        channel="ibm_cloud",
        token=api_key,
        instance=crn
    )

    print(">> Selecting least busy physical QPU...")
    backend = service.least_busy(operational=True, simulator=False)
    print(f">> Target backend: {backend.name}")
    print(f"   Qubits available: {backend.num_qubits}")
    print(f"   Basis gates: {backend.basis_gates}")
    return backend


def reconstruct_image(counts: dict, image_shape: tuple) -> np.ndarray:
    """
    Reconstructs the transmitted image via maximum likelihood estimation.

    With NUM_SHOTS measurements, the most frequently observed bitstring
    represents the maximum likelihood estimate of the transmitted state.
    This is statistically robust — unlike single-shot sampling which
    produces an arbitrary sample from the measurement distribution.

    Qiskit returns bitstrings in reversed qubit order (q_{n-1}...q_0).
    We correct this with reversed() before reshaping.

    Args:
        counts: Measurement outcome dictionary {bitstring: shot_count}.
        image_shape: Target shape for reconstruction.

    Returns:
        np.ndarray: Reconstructed binary image matrix.
    """
    most_probable = max(counts, key=counts.get)
    corrected = list(reversed(most_probable))
    flat = np.array([int(bit) for bit in corrected], dtype=np.uint8)
    return flat.reshape(image_shape)


def compute_metrics(original: np.ndarray,
                    reconstructed: np.ndarray,
                    backend_name: str) -> dict:
    """
    Computes transmission fidelity metrics for hardware execution results.

    Args:
        original: Ground truth binary image payload.
        reconstructed: Hardware-reconstructed image via MLE.
        backend_name: Name of the QPU used for execution.

    Returns:
        dict: Fidelity metrics including QBER, accuracy, and execution metadata.
    """
    error_count = int(np.sum(original != reconstructed))
    qber = (error_count / original.size) * 100

    return {
        "backend": backend_name,
        "timestamp": datetime.utcnow().isoformat(),
        "shots": NUM_SHOTS,
        "total_pixels": int(original.size),
        "error_count": error_count,
        "qber_percent": round(qber, 2),
        "accuracy_percent": round(100 - qber, 2),
        "protocol": "basis_encoding",
    }


def save_results(metrics: dict,
                 original: np.ndarray,
                 reconstructed: np.ndarray) -> None:
    """
    Persists hardware execution results to disk for dashboard and reporting.

    Saves:
      - JSON metrics file for the interactive dashboard
      - PNG comparison plot for the README and academic reporting

    Args:
        metrics: Fidelity metrics dictionary from compute_metrics().
        original: Original image payload.
        reconstructed: Hardware-reconstructed image.
    """
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Persist metrics as JSON for dashboard consumption
    with open(RESULTS_FILE, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f">> Metrics saved to {RESULTS_FILE}")

    # Generate comparison plot
    fig, axes = plt.subplots(1, 2, figsize=(8, 4))
    fig.suptitle(
        f"Basis Encoding — Physical Hardware Execution\n"
        f"Backend: {metrics['backend']} | "
        f"QBER: {metrics['qber_percent']}% | "
        f"Shots: {metrics['shots']}",
        fontsize=10
    )

    axes[0].imshow(original, cmap='Blues', vmin=0, vmax=1)
    axes[0].set_title("Original Payload")
    axes[0].axis('off')

    axes[1].imshow(reconstructed, cmap='Reds', vmin=0, vmax=1)
    axes[1].set_title(
        f"Hardware Reconstruction\n"
        f"QBER: {metrics['qber_percent']}% "
        f"({metrics['error_count']}/{metrics['total_pixels']} pixels)"
    )
    axes[1].axis('off')

    plt.tight_layout()
    plt.savefig(PLOT_FILE, dpi=150, bbox_inches='tight')
    plt.close()
    print(f">> Comparison plot saved to {PLOT_FILE}")


def execute_on_hardware() -> dict:
    """
    Orchestrates the full physical QPU execution pipeline.

    Pipeline:
      1. Load credentials from environment
      2. Build and encode the image payload circuit
      3. Authenticate and select backend
      4. Transpile circuit to backend native gate set
      5. Submit job via SamplerV2 primitives
      6. Retrieve results and reconstruct via MLE
      7. Compute fidelity metrics
      8. Persist results to disk

    Returns:
        dict: Fidelity metrics from the hardware run.
    """
    api_key, crn = load_credentials()
    original = create_payload()
    qc = build_circuit(original)

    backend = connect_to_backend(api_key, crn)

    # Transpile to backend's native gate set and qubit topology.
    # This step maps our logical circuit onto physical qubit connectivity —
    # may introduce additional SWAP gates depending on hardware topology.
    print(">> Transpiling circuit to native gate set...")
    transpiled_qc = transpile(qc, backend=backend, optimization_level=1)
    print(f"   Circuit depth after transpilation: {transpiled_qc.depth()}")
    print(f"   Gate count: {transpiled_qc.size()}")

    print(f">> Submitting job to {backend.name} ({NUM_SHOTS} shots)...")
    sampler = Sampler(mode=backend)
    job = sampler.run([transpiled_qc], shots=NUM_SHOTS)
    print(f">> Job submitted. ID: {job.job_id()}")
    print(">> Awaiting physical execution (queue time varies by global demand)...")

    result = job.result()
    counts = result[0].data.meas.get_counts()

    reconstructed = reconstruct_image(counts, original.shape)
    metrics = compute_metrics(original, reconstructed, backend.name)
    save_results(metrics, original, reconstructed)

    return metrics


if __name__ == "__main__":
    print("=" * 60)
    print("Physical QPU Execution — Basis Encoding Protocol")
    print(f"Shots: {NUM_SHOTS} | Protocol: Basis Encoding")
    print("=" * 60)

    try:
        metrics = execute_on_hardware()
        print("\n" + "=" * 60)
        print("HARDWARE EXECUTION COMPLETE")
        print(f"Backend:    {metrics['backend']}")
        print(f"Timestamp:  {metrics['timestamp']}")
        print(f"QBER:       {metrics['qber_percent']}%")
        print(f"Accuracy:   {metrics['accuracy_percent']}%")
        print(f"Errors:     {metrics['error_count']}/{metrics['total_pixels']} pixels")
        print("=" * 60)

    except EnvironmentError as e:
        print(f"\n[CREDENTIAL ERROR] {e}")
    except Exception as e:
        print(f"\n[EXECUTION ERROR] {e}")
        print("Common causes: expired API key, no available backends, "
              "network timeout, or job queue rejection.")
        raise