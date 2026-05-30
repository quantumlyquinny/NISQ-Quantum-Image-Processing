import numpy as np
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error

def create_payload():
    return np.array([
        [0, 1, 1, 0],
        [1, 1, 1, 1],
        [1, 1, 1, 1],
        [0, 1, 1, 0]
    ])

def run_amplitude_protocol(image_matrix, apply_noise=False):
    flat_image = image_matrix.flatten()
    num_pixels = len(flat_image)
    
    # We only need 4 qubits to represent 16 pixels (2^4 = 16 states)
    num_qubits = int(np.log2(num_pixels))
    qc = QuantumCircuit(num_qubits)
    
    # Step 1: Normalize classical data to represent valid quantum amplitudes
    # The sum of the squared amplitudes must equal exactly 1.0
    norm_factor = np.sqrt(np.sum(flat_image ** 2))
    normalized_amplitudes = flat_image / norm_factor
    
    # Step 2: The Brutal Part - State Preparation
    # This single line of Python compiles into dozens of noisy gates on physical hardware
    qc.initialize(normalized_amplitudes, range(num_qubits))
    
    # Step 3: TRANSMISSION CHANNEL
    for i in range(num_qubits):
        qc.id(i)
        
    qc.measure_all()
    
    # Step 4: Simulate the transmission
    simulator = AerSimulator()
    noise_model = NoiseModel()
    
    if apply_noise:
        # Crank the noise to 35% to overwhelm the classical error mitigation
        error_depol = depolarizing_error(0.35, 1)
        for q in range(num_qubits):
            noise_model.add_quantum_error(error_depol, ['id'], [q])
            
    # CRITICAL FIX: We must use high shots (8192) to rebuild the probability distribution
    result = simulator.run(qc, noise_model=noise_model, shots=8192).result()
    counts = result.get_counts()
    
    # Step 5: Reconstruct the image from the probability distribution
    reconstructed_flat = np.zeros(num_pixels)
    total_shots = sum(counts.values())
    
    # Map the binary string results back to physical pixel indices
    for bitstring, count in counts.items():
        # Qiskit reads right-to-left
        pixel_index = int(bitstring[::-1], 2)
        probability = count / total_shots
        
        # If the probability is above the background noise threshold, the pixel is "1"
        if probability > (0.5 / num_pixels): 
            reconstructed_flat[pixel_index] = 1
            
    return reconstructed_flat.reshape(image_matrix.shape)

if __name__ == "__main__":
    original = create_payload()
    print(">> Running Pristine Amplitude Encoding...")
    clean = run_amplitude_protocol(original, apply_noise=False)
    
    print(">> Running Noisy Amplitude Encoding...")
    noisy = run_amplitude_protocol(original, apply_noise=True)
    
    discrepancy = np.sum(original != noisy)
    qber = (discrepancy / original.size) * 100
    
    print(f">> Protocol Complete. Amplitude Degradation (QBER): {qber:.2f}%")