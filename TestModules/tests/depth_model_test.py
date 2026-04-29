"""Benchmark several depth-anything checkpoints in isolated subprocesses.

This is a manual harness, not a pytest case. It uses the new
``DepthAnythingMappingStrategy`` directly so each model load happens in its
own process and the timing is fair.
"""

from __future__ import annotations

import multiprocessing
import os
import time

import cv2

from avroom_object_removal.ai_engines.depth.strategies.depth_anything_mapping_strategy import (
    DepthAnythingMappingStrategy,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def run_model_task(model_name: str, image_path: str, out_path: str) -> None:
    """Load ``model_name``, depth-map ``image_path``, save PNG to ``out_path``."""
    try:
        image = cv2.imread(image_path)
        if image is None:
            print(f"Error loading image for {model_name}")
            return

        strategy = DepthAnythingMappingStrategy(model_name=model_name)
        depth = strategy.map_depth(image)
        cv2.imwrite(out_path, depth)
    except Exception as e:
        print(f"Failed inside process for {model_name}. Error: {e}")


def test_different_models() -> None:
    image_path = os.path.join(BASE_DIR, "..", "inputs", "test.jpg")

    output_dir = os.path.join(BASE_DIR, "..", "outputs", "depthMaps")
    os.makedirs(output_dir, exist_ok=True)

    log_file_path = os.path.join(output_dir, "time_log.txt")
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
        "Intel/dpt-large",
        "Intel/zoedepth-nyu-kitti",
        "depth-anything/Depth-Anything-V2-Metric-Indoor-Large-hf",
    ]

    timeout_seconds = 15.0

    for model_name in models_to_test:
        print(f"\n[{model_name}] Starting... (Timeout: {timeout_seconds}s)")

        safe_name = model_name.replace("/", "_").replace("\\", "_")
        out_path = os.path.join(output_dir, f"{safe_name}.png")

        proc = multiprocessing.Process(
            target=run_model_task, args=(model_name, image_path, out_path)
        )

        start_time = time.time()
        proc.start()
        proc.join(timeout_seconds)

        with open(log_file_path, "a", encoding="utf-8") as log_file:
            if proc.is_alive():
                print(
                    f"[{model_name}] TIMEOUT! Took longer than {timeout_seconds}s. Killing..."
                )
                proc.terminate()
                proc.join()
                log_file.write(
                    f"Model: {model_name}\nStatus: TIMEOUT (> {timeout_seconds}s)\n\n"
                )
            else:
                elapsed = time.time() - start_time
                print(f"[{model_name}] Success! Completed in {elapsed:.2f} seconds.")
                log_file.write(
                    f"Model: {model_name}\nStatus: SUCCESS\nTime: {elapsed:.2f} seconds\n\n"
                )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    test_different_models()
