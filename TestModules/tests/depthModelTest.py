import os
import cv2
import multiprocessing
import time

# Define paths and imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from avroom_object_removal.ai_engines.depth.ImageDepthMapper import ImageDepthMapper

# Moved function to global scope to prevent Pickle error on Windows
def run_model_task(model_name, image_path, out_path):
    try:
        image = cv2.imread(image_path)
        if image is None:
            print(f"Error loading image for {model_name}")
            return
            
        mapper = ImageDepthMapper()
        mapper.model = model_name
        
        # Save the generated depth map image directly to the out_path
        mapper.get_depth_map(image, output_path=out_path)
    except Exception as e:
        print(f"Failed inside process for {model_name}. Error: {e}")

def test_different_models():
    image_path = os.path.join(BASE_DIR, "..", "inputs", "test.jpg")
    
    # Define and ensure the output directory exists
    output_dir = os.path.join(BASE_DIR, "..", "outputs", "depthMaps")
    os.makedirs(output_dir, exist_ok=True)
    
    # Define the log file path
    log_file_path = os.path.join(output_dir, "time_log.txt")
    
    # Initialize the log file with a header (overwrites previous runs)
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write("Depth Models Benchmark Results\n")
        log_file.write("==============================\n\n")
    
    models_to_test = [
        "LiheYoung/depth-anything-small-hf",
        "depth-anything/Depth-Anything-V2-Small-hf",
        "depth-anything/Depth-Anything-V2-Metric-Indoor-Base-hf",
        "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf",
        "Intel/dpt-hybrid-midas",
        "Intel/dpt-swinv2-tiny-256",
        "vinvino02/glpn-nyu",
        # Heavy models - uncomment if you want to test them with a larger timeout
         "Intel/dpt-large",
         "Intel/zoedepth-nyu-kitti",
         "depth-anything/Depth-Anything-V2-Metric-Indoor-Large-hf",
    ]

    # Define maximum run time
    TIMEOUT_SECONDS = 15.0 

    for model_name in models_to_test:
        print(f"\n[{model_name}] Starting... (Timeout: {TIMEOUT_SECONDS}s)")
        
        # Sanitize model name for safe file saving
        safe_name = model_name.replace('/', '_').replace('\\', '_')
        out_path = os.path.join(output_dir, f"{safe_name}.png")

        # Create a new isolated process
        p = multiprocessing.Process(target=run_model_task, args=(model_name, image_path, out_path))
        
        start_time = time.time()
        p.start()
        
        # Wait until the timeout limit
        p.join(TIMEOUT_SECONDS)

        # Open log file in append mode to record the result of this model
        with open(log_file_path, "a", encoding="utf-8") as log_file:
            # If the process is still alive after the timeout, kill it and log timeout
            if p.is_alive():
                print(f"[{model_name}] TIMEOUT! Took longer than {TIMEOUT_SECONDS}s. Killing process...")
                p.terminate()
                p.join()
                log_file.write(f"Model: {model_name}\nStatus: TIMEOUT (> {TIMEOUT_SECONDS}s)\n\n")
            else:
                elapsed = time.time() - start_time
                print(f"[{model_name}] Success! Completed in {elapsed:.2f} seconds.")
                log_file.write(f"Model: {model_name}\nStatus: SUCCESS\nTime: {elapsed:.2f} seconds\n\n")

if __name__ == "__main__":
    # This protection line is mandatory in Windows when using multiprocessing
    multiprocessing.freeze_support() 
    test_different_models()
