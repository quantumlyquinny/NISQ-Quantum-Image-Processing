import numpy as np
import matplotlib.pyplot as plt
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, pauli_error

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
        # Define NISQ-era operational imperfections
        p_depol = 0.05
        p_bitflip = 0.02
        
        error_depol = depolarizing_error(p_depol, 1)
        error_bitflip = pauli_error([('X', p_bitflip), ('I', 1 - p_bitflip)])
        
        # Inject custom errors into single-qubit operations
        noise_model.add_all_qubit_quantum_error(error_depol, ['x'])
        noise_model.add_all_qubit_quantum_error(error_bitflip, ['x'])
        
    # Execute circuit
    result = simulator.run(qc, noise_model=noise_model, shots=1024).result()
    counts = result.get_counts()
    
    # Retrieve the dominant measured bitstring state
    most_frequent_state = max(counts, key=counts.get)
    
    # Reconstruct the 1D bitstring sequence back to a 4x4 grid
    reconstructed_flat = np.array([int(bit) for bit in reversed(most_frequent_state)])
    return reconstructed_flat.reshape(image_matrix.shape)

if __name__ == "__main__":
    original = create_payload()
    print(">> Processing pristine local simulation...")
    clean_output = encode_and_simulate(original, apply_noise=False)
    
    print(">> Injecting depolarizing and bit-flip environmental noise...")
    noisy_output = encode_and_simulate(original, apply_noise=True)
    
    # Compute error metrics
    discrepancy = np.sum(original != noisy_output)
    qber = (discrepancy / original.size) * 100
    print(f">> Simulation complete. Observed Quantum Bit Error Rate (QBER): {qber:.2f}%")