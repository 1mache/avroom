import sys
import os
from transformers import pipeline

def warmup_models():
    print("Starting Model Warmup (Caching) Process...")
    print("This script will download the models to your local huggingface cache.")
    print("It might take a few minutes depending on your internet speed.\n")

    # The exact list of lightweight models we want to benchmark
    models_to_cache = [
        "LiheYoung/depth-anything-small-hf",
        "depth-anything/Depth-Anything-V2-Small-hf",
        "vinvino02/glpn-nyu",
        "Intel/dpt-swinv2-tiny-256",
        # Adding the "Base" version just in case you want to test a slightly larger model
        "depth-anything/Depth-Anything-V2-Metric-Indoor-Base-hf" 
    ]

    for model_name in models_to_cache:
        print(f"--------------------------------------------------")
        print(f"Checking/Downloading Model: {model_name}")
        try:
            # We initialize the pipeline. 
            # If the model is not in cache, Hugging Face will download it.
            # If it is, it will just load it silently (super fast).
            pipe = pipeline(task="depth-estimation", model=model_name)
            print(f"[SUCCESS] {model_name} is fully cached and ready!")
        except Exception as e:
            print(f"[ERROR] Failed to download {model_name}. Error: {e}")
            
    print("\n--------------------------------------------------")
    print("Warmup Complete! All models are cached.")
    print("You can now run your depthModelTest.py with the 15s timeout fairly.")

if __name__ == "__main__":
    warmup_models()