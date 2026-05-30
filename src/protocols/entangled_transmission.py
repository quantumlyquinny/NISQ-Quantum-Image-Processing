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

def run_entangled_protocol(image_matrix, apply_noise=False):
    flat_image = image_matrix.flatten()
    num_pixels = len(flat_image)
    
    # We need 2 qubits per pixel for entanglement (32 qubits total)
    qc = QuantumCircuit(num_pixels * 2)
    
    # Step 1: Create Bell States (Entangled Pairs)
    for i in range(num_pixels):
        qc.h(i * 2)               # Alice's qubit
        qc.cx(i * 2, i * 2 + 1)   # Entangle with Bob's qubit
        
    # Step 2: Alice encodes the image payload using Phase Flips (Z gate)
    for idx, pixel in enumerate(flat_image):
        if pixel == 1:
            qc.z(idx * 2)
            
    # Step 3: TRANSMISSION CHANNEL (Bob's qubits travel through space)
    for i in range(num_pixels):
        qc.id(i * 2 + 1)  # Explicit identity gate representing time spent in transit
        
    # Step 4: Bob receives the qubits and decodes by reversing the Bell state
    for i in range(num_pixels):
        qc.cx(i * 2, i * 2 + 1)
        qc.h(i * 2)
        
    qc.measure_all()
    
    # Step 5: Simulate the transmission
    simulator = AerSimulator(method='stabilizer')
    noise_model = NoiseModel()
    
    if apply_noise:
        # Inject transmission noise on Bob's receiving qubits during transit
        error_depol = depolarizing_error(0.15, 1)
        bobs_qubits = [i * 2 + 1 for i in range(num_pixels)]
        for q in bobs_qubits:
            # Catch the 'id' gate we added during transmission
            noise_model.add_quantum_error(error_depol, ['id'], [q])
        
    result = simulator.run(qc, noise_model=noise_model, shots=1).result()
    counts = result.get_counts()
    received_state = list(counts.keys())[0]
    
    reversed_state = received_state[::-1]
    decoded_bits = [int(reversed_state[i * 2]) for i in range(num_pixels)]
    
    reconstructed_flat = np.array(decoded_bits)
    return reconstructed_flat.reshape(image_matrix.shape)

if __name__ == "__main__":
    original = create_payload()
    print(">> Running Pristine Entangled Transmission...")
    clean = run_entangled_protocol(original, apply_noise=False)
    
    print(">> Running Noisy Entangled Transmission...")
    noisy = run_entangled_protocol(original, apply_noise=True)
    
    discrepancy = np.sum(original != noisy)
    qber = (discrepancy / original.size) * 100
    
    print(f">> Protocol Complete. Entanglement Degradation (QBER): {qber:.2f}%")