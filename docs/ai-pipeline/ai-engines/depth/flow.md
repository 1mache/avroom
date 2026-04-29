# Depth execution and data flow

1. Near model (`depth-anything/Depth-Anything-V2-Small-hf`) predicts depth.
2. Far model (`LiheYoung/depth-anything-small-hf`) predicts depth.
3. Both outputs normalized to uint8 0–255 per strategy logic.
4. Near depth used as alpha weights for compositing over far depth (soft blend, not simple averaging).

Single grayscale tensor flows to [`SamImageAdapter`](../../../../TestModules/src/ai_engines/segmentation/sam_image_adapter.py) and to routing for boundary statistics.
