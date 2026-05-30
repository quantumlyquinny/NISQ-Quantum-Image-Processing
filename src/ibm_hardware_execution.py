import os
import numpy as np
from dotenv import load_dotenv
from qiskit import QuantumCircuit, transpile
from qiskit_ibm_runtime import QiskitRuntimeService
from qiskit_ibm_runtime import SamplerV2 as Sampler

# Load the hidden credentials from the .env file
load_dotenv()
api_key = os.getenv("IBM_API_KEY")
crn = os.getenv("IBM_CRN")

def create_payload():
    return np.array([
        [0, 1, 1, 0],
        [1, 1, 1, 1],
        [1, 1, 1, 1],
        [0, 1, 1, 0]
    ])

def execute_on_hardware():
    image_matrix = create_payload()
    flat_image = image_matrix.flatten()
    num_qubits = len(flat_image)
    
    # 1. Construct the data packet
    qc = QuantumCircuit(num_qubits)
    for idx, pixel in enumerate(flat_image):
        if pixel == 1:
            qc.x(idx)
    qc.measure_all()
    
    # 2. Authenticate with IBM Cloud Quantum Instance
    print(">> Authenticating with IBM Quantum Cloud...")
    service = QiskitRuntimeService(
        channel="ibm_cloud",
        token=api_key,       
        instance=crn         
    )
    
    # 3. Locate the most optimal physical quantum computer
    print(">> Finding the least busy physical quantum computer...")
    backend = service.least_busy(operational=True, simulator=False)
    print(f">> Target locked: {backend.name}")
    
    # 4. Transpile (compile) the circuit for the specific QPU topology
    print(">> Compiling circuit for physical hardware...")
    transpiled_qc = transpile(qc, backend=backend)
    
    # 5. Transmit the payload using the Primitives interface (Sampler V2)
    print(">> Transmitting payload to physical quantum queue via Sampler...")
    sampler = Sampler(mode=backend)
    job = sampler.run([transpiled_qc], shots=1)
    print(f">> Job successfully submitted! Tracking ID: {job.job_id()}")
    print(">> Waiting for physical execution (this may take a few minutes depending on global queue)...")
    
    # 6. Retrieve and process V2 results
    result = job.result()
    # V2 Primitives nest the counts inside the classical register data ('meas')
    counts = result[0].data.meas.get_counts()
    received_state = list(counts.keys())[0]
    
    reconstructed_flat = np.array([int(bit) for bit in reversed(received_state)])
    noisy_output = reconstructed_flat.reshape(image_matrix.shape)
    
    # 7. Calculate actual hardware degradation
    discrepancy = np.sum(image_matrix != noisy_output)
    qber = (discrepancy / image_matrix.size) * 100
    
    print("\n========================================")
    print(f">> HARDWARE RUN COMPLETE")
    print(f">> Target Machine: {backend.name}")
    print(f">> Observed Physical QBER: {qber:.2f}%")
    print("========================================")

if __name__ == "__main__":
    execute_on_hardware()