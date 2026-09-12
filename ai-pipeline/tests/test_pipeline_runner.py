import os
import shutil
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from avroom_object_removal import ObjectRemover

# Configure basic logging for the test script
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TestRunner")

# ==========================================
# TEST CONFIGURATION
# ==========================================
# Update this to the exact path of your test image
IMAGE_PATH = os.path.join(os.path.dirname(__file__), "..", "inputs", "test.jpg")

# Replace these with the actual (X, Y) coordinates from your image!
POINTS_TO_TEST = [
    (825, 825),   # 1. The Grey Pouf
    (1484, 456),  # 2. The TV on the right
    (350, 400)    # 3. The Window in the background (Approximate)
]

# Directory setup
OUTPUTS_DIR = os.path.join(BASE_DIR, "..", "outputs")
TEST_RESULTS_DIR = os.path.join(OUTPUTS_DIR, "script_test_outputs")

def setup_directories():
    """Creates the main test output directory."""
    if not os.path.exists(TEST_RESULTS_DIR):
        os.makedirs(TEST_RESULTS_DIR)
        logger.info(f"Created test results directory at: {TEST_RESULTS_DIR}")

def move_outputs_to_test_folder(run_index: int):
    """
    Moves all newly generated files from the main outputs folder 
    into a specific numbered sub-folder for the current test run.
    """
    target_dir = os.path.join(TEST_RESULTS_DIR, str(run_index))
    os.makedirs(target_dir, exist_ok=True)
    
    # We move all files in the output directory (excluding our test results directory itself)
    moved_count = 0
    for item in os.listdir(OUTPUTS_DIR):
        item_path = os.path.join(OUTPUTS_DIR, item)
        
        # Only move files (not directories)
        if os.path.isfile(item_path):
            shutil.move(item_path, os.path.join(target_dir, item))
            moved_count += 1
            
    logger.info(f"Moved {moved_count} files to {target_dir}")

def main():
    logger.info("Starting Automated Pipeline Test...")
    setup_directories()
    
    # Initialize the engine once (loads SAM, LaMa, and SD to memory)
    logger.info("Initializing AI engines. This may take a minute...")
    remover = ObjectRemover()
    
    for i, (x, y) in enumerate(POINTS_TO_TEST):
        run_index = i + 1
        logger.info("=" * 50)
        logger.info(f"RUN {run_index}: Testing point ({x}, {y})")
        logger.info("=" * 50)
        
        try:
            # 1. Execute the removal
            remover.remove_object(IMAGE_PATH, x, y)
            
            # 2. Archive the results
            move_outputs_to_test_folder(run_index)
            
            logger.info(f"Run {run_index} completed successfully.")
            
        except Exception as e:
            logger.error(f"Run {run_index} FAILED at point ({x}, {y}). Error: {str(e)}")
            
    logger.info("Automated testing finished completely. Check the outputs folder!")

if __name__ == "__main__":
    main()
