# Inpainting contracts

- **Inputs:** BGR scene `np.ndarray`, binary or gray mask matching H/W, optional kwargs (`strength` from router translates to SD participation).
- **Output:** BGR `np.ndarray`, same spatial size as input image.

Hybrid decides internally whether SD runs based on threshold vs supplied strength.
