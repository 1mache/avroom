import os
import cv2
import numpy as np
from ImageDepthMapper import ImageDepthMapper
from objectRemover import ObjectRemover

class GuiTestClicker:
    """Simple GUI helper to pick a point in an image and trigger object removal.

    This class displays an image using OpenCV and waits for the user to click
    a point. Once the click occurs it configures an :class:`ObjectRemover`
    instance and invokes ``removeObjectTest`` with the selected point.
    """

    def __init__(self, object_remover: ObjectRemover | None = None):
        # allow caller to supply their own remover or create a default one
        self.remover = object_remover or ObjectRemover()
        self._image_path: str | None = None
        self._click_point: tuple[int, int] | None = None

    def _mouse_callback(self, event, x, y, flags, param):
        # only care about left button down
        if event == cv2.EVENT_LBUTTONDOWN:
            self._click_point = (x, y)
            # set the fields on the remover and trigger removal
            if self._image_path is not None:
                self.remover.set_image(self._image_path)
                self.remover.set_point(x, y)
                # call test helper; leave depth map saving unspecified
                self.remover.removeObjectTest()

                # close the window after performing the removal
                cv2.destroyAllWindows()

    def run(self, image_path: str) -> None:
        """Open the image at ``image_path`` and wait for a click.

        After the user clicks the displayed image, ``removeObjectTest`` is
        invoked on the configured :class:`ObjectRemover` with the chosen
        coordinates.
        """
        self._image_path = image_path
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Cannot load image: {image_path}")

        # downscale for display if the image is too large
        max_dim = 800  # maximum width or height
        h, w = image.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        window_name = "Select point to remove object"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(window_name, self._mouse_callback)

        while True:
            cv2.imshow(window_name, image)
            key = cv2.waitKey(20) & 0xFF
            # break on ESC or after click handled
            if key == 27 or self._click_point is not None:
                break

        cv2.destroyAllWindows()


def main():
    """Manual runner for quick testing."""
    clicker = GuiTestClicker()
    ImageDepthMapper().model = "LiheYoung/depth-anything-small-hf"  # ensure we're using the expected model
    default_image = os.path.join(os.path.dirname(__file__), "..", "inputs", "test.jpg")
    clicker.run(default_image)

if __name__ == "__main__":
    main()