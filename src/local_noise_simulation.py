import numpy as np
import matplotlib.pyplot as plt
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, pauli_error

def create_payload():
    """Generates a simple 4x4 binary image payload (e.g., a cross pattern)."""
    return np.array([
        [0, 1, 1, 0],
        [1, 1, 1, 1],
        [1, 1, 1, 1],
        [0, 1, 1, 0]
    ])

def encode_and_simulate(image_matrix, apply_noise=False):
    """Encodes a 2D pixel array into a 1D basis state configuration."""
    flat_image = image_matrix.flatten()
    num_qubits = len(flat_image)
    
    # Instantiate quantum circuit representing the data packet
    qc = QuantumCircuit(num_qubits)
    
    # Simple basis encoding: Apply an X gate where the pixel bit value is 1
    for idx, pixel in enumerate(flat_image):
        if pixel == 1:
            qc.x(idx)
            
    qc.measure_all()
    
    # Configure simulator and hardware-aware noise parameters
    simulator = AerSimulator()
    noise_model = NoiseModel()
    
    if apply_noise:
        # 1. Define NISQ-era readout error (10% error rate for visibility)
        p_readout = 0.10
        
        # 2. Apply noise to the MEASUREMENT phase so it affects all qubits
        error_meas = pauli_error([('X', p_readout), ('I', 1 - p_readout)])
        noise_model.add_all_qubit_quantum_error(error_meas, ['measure'])
            
    # 3. CRITICAL FIX: shots=1 simulates a single, realistic transmission payload
    result = simulator.run(qc, noise_model=noise_model, shots=1).result()
    counts = result.get_counts()
    
    # Retrieve the only measured bitstring state (since shots=1)
    received_state = list(counts.keys())[0]
    
    # Reconstruct the 1D bitstring sequence back to a 4x4 grid
    reconstructed_flat = np.array([int(bit) for bit in reversed(received_state)])
    return reconstructed_flat.reshape(image_matrix.shape)

if __name__ == "__main__":
    original = create_payload()
    print(">> Processing pristine local simulation...")
    clean_output = encode_and_simulate(original, apply_noise=False)
    
    print(">> Injecting measurement readout noise...")
    noisy_output = encode_and_simulate(original, apply_noise=True)
    
    # Compute error metrics
    discrepancy = np.sum(original != noisy_output)
    qber = (discrepancy / original.size) * 100
    print(f">> Simulation complete. Observed Quantum Bit Error Rate (QBER): {qber:.2f}%")