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

def run_watermarking_protocol(image_matrix, apply_noise=False):
    flat_image = image_matrix.flatten()
    num_pixels = len(flat_image)
    
    # 1 qubit per pixel (16 qubits total)
    qc = QuantumCircuit(num_pixels)
    
    # Define a static pattern for watermark check positions (e.g., corners and center pixels)
    # 1 indicates a fragile watermark pixel, 0 indicates a standard data pixel
    watermark_mask = np.array([
        [1, 0, 0, 1],
        [0, 1, 1, 0],
        [0, 1, 1, 0],
        [1, 0, 0, 1]
    ]).flatten()
    
    # Step 1: Alice encodes the payload
    for idx, is_watermark in enumerate(watermark_mask):
        if is_watermark == 1:
            # Place watermark pixels into a fragile superposition state
            qc.h(idx)
        else:
            # Encode standard image data using basis encoding (Pauli-X)
            if flat_image[idx] == 1:
                qc.x(idx)
                
    # Step 2: TRANSMISSION CHANNEL (All qubits travel through the noisy channel)
    for i in range(num_pixels):
        qc.id(i)
        
    # Step 3: Bob receives and decodes the payload
    for idx, is_watermark in enumerate(watermark_mask):
        if is_watermark == 1:
            # Reverse the Hadamard to bring pristine watermarks back to |0>
            qc.h(idx)
            
    qc.measure_all()
    
    # Step 4: Simulate the transmission
    simulator = AerSimulator()
    noise_model = NoiseModel()
    
    if apply_noise:
        # Introduce a 10% depolarizing error across the transit lines
        error_depol = depolarizing_error(0.10, 1)
        for q in range(num_pixels):
            noise_model.add_quantum_error(error_depol, ['id'], [q])
            
    result = simulator.run(qc, noise_model=noise_model, shots=1).result()
    counts = result.get_counts()
    received_state = list(counts.keys())[0]
    
    # Qiskit orders bits right-to-left, so flip the string for tracking match
    reversed_state = received_state[::-1]
    decoded_bits = [int(bit) for bit in reversed_state]
    
    # Evaluate the structural integrity of our watermark sentinels
    watermark_errors = 0
    total_watermarks = np.sum(watermark_mask)
    
    for idx, is_watermark in enumerate(watermark_mask):
        if is_watermark == 1:
            # Pristine watermark bits should decode strictly to 0
            if decoded_bits[idx] != 0:
                watermark_errors += 1
                
    watermark_qber = (watermark_errors / total_watermarks) * 100 if total_watermarks > 0 else 0.0
    reconstructed_flat = np.array(decoded_bits)
    
    return reconstructed_flat.reshape(image_matrix.shape), watermark_qber

if __name__ == "__main__":
    original = create_payload()
    print(">> Running Pristine Quantum Watermarking Protocol...")
    clean_img, clean_w_qber = run_watermarking_protocol(original, apply_noise=False)
    print(f">> Clean Run Watermark QBER: {clean_w_qber:.2f}%")
    
    print("\n>> Running Noisy Quantum Watermarking Protocol...")
    noisy_img, noisy_w_qber = run_watermarking_protocol(original, apply_noise=True)
    print(f">> Noisy Run Watermark QBER: {noisy_w_qber:.2f}%")