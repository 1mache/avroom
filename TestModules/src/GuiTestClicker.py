import os
import cv2
import logging
from core.objectRemover import ObjectRemover

# Configure logging
logger = logging.getLogger(__name__)

class GuiTestClicker:
    """
    Simple GUI helper to pick a point in an image and trigger object removal.
    Integrated with Architectural Facades and Logging.
    """
    def __init__(self, object_remover: ObjectRemover | None = None):
        self.remover = object_remover or ObjectRemover()
        self._image_path: str | None = None
        self._click_point: tuple[int, int] | None = None
        logger.info("GuiTestClicker initialized")

    def _mouse_callback(self, event, x, y, flags, param):
        # only care about left button down
        if event == cv2.EVENT_LBUTTONDOWN:
            logger.info(f"Click detected at ({x}, {y})")
            
            if self._image_path is not None:
                print(f"[GUI] Click detected at ({x}, {y}). Starting removal pipeline...")
                logger.info(f"Starting removal pipeline for image: {self._image_path}")
                
                # Configure the remover with state
                self.remover.set_image(self._image_path)
                self.remover.set_point(x, y)
                
                # Trigger the removal
                self.remover.remove_object_test()

                # Close the window after performing the removal
                cv2.destroyAllWindows()
                logger.info("Removal pipeline completed.")
                self._click_point = (x, y) # Set this to break the loop

    def run(self, image_path: str) -> None:
        """Open the image at `image_path` and wait for a click."""
        logger.info(f"Loading image: {image_path}")
        self._image_path = image_path
        image = cv2.imread(image_path)
        
        if image is None:
            logger.error(f"Cannot load image: {image_path}")
            raise FileNotFoundError(f"Cannot load image: {image_path}")

        # FIX: We NO LONGER resize the image array. This keeps the coordinates accurate!
        # Instead, we just make the display window larger.
        window_name = "Select point to remove object"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        # Make the window large and comfortable (e.g., 1280x720)
        cv2.resizeWindow(window_name, 1280, 720)
        cv2.setMouseCallback(window_name, self._mouse_callback)

        print(f"[GUI] Window opened. Click on an object in the image...")
        logger.info("GUI window opened. Awaiting user click...")
        
        while True:
            cv2.imshow(window_name, image)
            key = cv2.waitKey(20) & 0xFF
            # break on ESC or after click handled
            if key == 27 or self._click_point is not None:
                break

        cv2.destroyAllWindows()

def setup_logging():
    """Setup logging to outputs folder"""
    outputs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    
    log_file = os.path.join(outputs_dir, "application.log")
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

def main():
    """Manual runner for quick testing."""
    setup_logging()
    logger.info("=" * 60)
    logger.info("Application started")
    logger.info("=" * 60)
    
    clicker = GuiTestClicker()
    current_dir = os.path.dirname(os.path.abspath(__file__))
    default_image = os.path.join(current_dir, "..", "inputs", "test.jpg")
    
    if not os.path.exists(default_image):
        logger.error(f"Test image not found at: {default_image}")
        print(f"[Error] Test image not found at: {default_image}")
        return

    clicker.run(default_image)
    logger.info("Application finished")

if __name__ == "__main__":
    main()