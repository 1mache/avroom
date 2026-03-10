import os
import cv2
import numpy as np
from PIL import Image

from ImageDepthMapper import ImageDepthMapper
from LamaInpainter import LamaFacade
from SamFacadeSingleton import SamFacadeSingleton
from imageAdapterFactory import ImageAdapterFactory


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CHECKPOINT_PATH = os.path.join(BASE_DIR, "..", "checkpoints", "sam_vit_b_01ec64.pth")
IMAGE_PATH = os.path.join(BASE_DIR, "..", "inputs", "test.jpg")
DEPTH_MAP_PATH = os.path.join(BASE_DIR, "..", "inputs", "testDepthMap.png")
OUTPUT_PATH = os.path.join(BASE_DIR, "..", "outputs", "result_removal.png")
MASK_OUTPUT_PATH = os.path.join(BASE_DIR, "..", "outputs", "result_mask_separation.jpg")
MASK_OUTPUT_PATH_ORIGIN = os.path.join(BASE_DIR, "..", "outputs", "result_mask_separation_origin.jpg")
RESULT_INVERTED_MASK = os.path.join(BASE_DIR, "..", "outputs", "result_inverted_mask.jpg")


class ObjectRemover:
    def __init__(self):
        self.sam = SamFacadeSingleton()
        self.lama = LamaFacade()
        self.depth = ImageDepthMapper()
        self.image_adapter = ImageAdapterFactory()

        # fields that can be set externally for testing or reuse
        self.image_path: str | None = None
        # store coordinates as a numpy array [x, y]
        self.coordinates: np.ndarray | None = None

    def expand_mask(self, mask, pixels_to_expand=3):
        mask = np.array(mask)
        if mask.max() <= 1:
            mask = (mask * 255).astype(np.uint8)
        else:
            mask = mask.astype(np.uint8)
        k_size = int((2 * pixels_to_expand) + 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
        expanded_mask = cv2.dilate(mask, kernel, iterations=1)
        return expanded_mask

    def remove_object(self, image_path, click_x, click_y, depth_output_path: str | None = None):
        # core removal implementation expects explicit parameters
        image = cv2.imread(image_path)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        depth_map = self.depth.get_depth_map(image_path, output_path=depth_output_path)
        # optionally save the retrieved depth map
        depth_map_adapter = self.image_adapter.create_image(depth_map)
        best_mask = self.sam.get_mask_at_point(depth_map_adapter, (click_x, click_y))
        print("segmentation finished")
        
        self.saveMask(best_mask, MASK_OUTPUT_PATH_ORIGIN)
        best_mask = self.expand_mask(best_mask, 30)
        self.saveMask(best_mask, MASK_OUTPUT_PATH)
        
        inverted_mask = cv2.bitwise_not(best_mask)
        self.saveMask(inverted_mask, RESULT_INVERTED_MASK)
        
        print("--- Step 3: Inpainting (LaMa) ---")
        print("about to start inpainting")
        
        result = self.lama.inpaint(image, best_mask)
        print("inpainting finished")
        result_image = Image.fromarray(result)
        result_image.save(OUTPUT_PATH)

    def saveMask(self, mask, path):
        print("saving mask")
        mask = np.array(mask, copy=False)
        if mask.max() <= 1:
            mask = (mask * 255).astype(np.uint8)
        else:
            mask = mask.astype(np.uint8)
        cv2.imwrite(path, mask)

    # --- convenience setters / test helpers ---

    def set_image(self, image_path: str) -> None:
        """Store image path for later operations."""
        self.image_path = image_path

    def set_point(self, x: float, y: float) -> None:
        """Set the click/coordinates used for segmentation.

        Coordinates are stored as a NumPy array for convenience.
        """
        # convert to float/numeric type in case callers pass ints
        self.coordinates = np.array([x, y], dtype=float)

    def removeObjectTest(self, depth_save_path: str | None = None) -> None:
        """Wrapper that calls :meth:`remove_object` using the stored fields.

        This is useful for simple scripted tests or external callers that
        configure the object remover via its setters.

        Args:
            depth_save_path: if provided, the depth map returned by the
                sampler will be written to this file before segmentation.
        """
        if self.image_path is None:
            raise ValueError("image_path has not been set")
        if self.coordinates is None or self.coordinates.size != 2:
            raise ValueError("coordinates have not been set")

        x, y = self.coordinates.tolist()
        self.remove_object(self.image_path, x, y, depth_output_path=depth_save_path)


def main():
    object_remover = ObjectRemover()
    
    # example usage of the original interface
    # ObjectRemover().remove_object(IMAGE_PATH, DEPTH_MAP_PATH, 910, 801)

    # example usage of the new setters and test helper
    object_remover.set_image(IMAGE_PATH)
    object_remover.set_point(910, 801)
    # if you want to see the intermediate depth map, pass a path
    object_remover.removeObjectTest(depth_save_path=os.path.join(BASE_DIR, "..", "outputs", "debug_depth.png"))


if __name__ == "__main__":
    main()
