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

    def remove_object(self, image_path, depth_map_path, click_x, click_y):
        image = cv2.imread(image_path)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        depth_map = self.depth.get_depth_map(image_path)
        depth_map_adapter = self.image_adapter.create_image(depth_map_path)
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


def main():
    ObjectRemover().remove_object(IMAGE_PATH, DEPTH_MAP_PATH, 910, 801)


if __name__ == "__main__":
    main()
