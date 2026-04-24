import os
import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from avroom_object_removal.ai_engines.segmentation.SamFacadeSingleton import SamFacadeSingleton
from avroom_object_removal.ai_engines.depth.ImageDepthMapper import ImageDepthMapper
from avroom_object_removal.utils.imageAdapterFactory import ImageAdapterFactory


def test_sam_models():
    """
    Run SAM mask generation using different depth map models as input.
    Combines all generated masks into a single colorized image per model 
    to easily visualize object separation.
    """
    image_path = os.path.join(BASE_DIR, "..", "inputs", "test.jpg")
    orig_image = cv2.imread(image_path)
    if orig_image is None:
        print(f"Error: could not load image at {image_path}")
        return

    # Initialize singletons
    depth_mapper = ImageDepthMapper()
    adapter = ImageAdapterFactory()
    sam = SamFacadeSingleton()

    # The 3 fastest, fully cached models
    models_to_test = [
        "LiheYoung/depth-anything-small-hf",
        "depth-anything/Depth-Anything-V2-Small-hf",
        "Intel/dpt-swinv2-tiny-256"
    ]

    out_base = os.path.join(BASE_DIR, "..", "outputs", "depthMapsSAMall")
    os.makedirs(out_base, exist_ok=True)

    for model_name in models_to_test:
        print(f"\n==================================================")
        print(f"Generating combined mask image for: {model_name}")
        
        try:
            # 1. Set the depth model
            depth_mapper.model = model_name 
            
            # 2. Generate depth map
            depth_map = depth_mapper.get_depth_map(orig_image)
            
            # 3. Adapt the depth map for SAM
            adapted_image = adapter.create_image(depth_map) 
            
            if not isinstance(adapted_image, np.ndarray):
                adapted_image = np.array(adapted_image)
                if len(adapted_image.shape) == 2:
                    adapted_image = cv2.cvtColor(adapted_image, cv2.COLOR_GRAY2RGB)
                elif adapted_image.shape[2] == 4:
                    adapted_image = cv2.cvtColor(adapted_image, cv2.COLOR_RGBA2RGB)

            # 4. Get all masks from SAM
            masks = sam.get_all_masks(adapted_image)
            
            # 5. Create a blank black image with the same dimensions as the original
            combined_mask_img = np.zeros_like(orig_image)
            
            # 6. Apply a random color to each mask and add it to the combined image
            for mask in masks:
                # Generate a random BGR color (avoiding pure black)
                color = np.random.randint(50, 255, (3,), dtype=np.uint8)
                
                # Ensure mask is a boolean array (True where the object is)
                bool_mask = mask > 0
                
                # Apply the color to the areas where the mask exists
                combined_mask_img[bool_mask] = color
                
            # 7. Sanitize model name and save the single combined image
            safe_model_name = model_name.replace('/', '_').replace('\\', '_')
            out_path = os.path.join(out_base, f"{safe_model_name}_combined.png")
            cv2.imwrite(out_path, combined_mask_img)
                
            print(f"[SUCCESS] Saved combined image with {len(masks)} separated objects to {out_path}")
            
        except Exception as e:
            print(f"[ERROR] Failed to process with model {model_name}. Error: {e}")

if __name__ == "__main__":
    test_sam_models()
