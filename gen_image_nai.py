# gen_image_nai.py
import requests
import json
import sys
import random
import os
import zipfile
from io import BytesIO

with open("apitoken.json") as f:
    api_token = json.load(f)["token"]


def generate_image(prompt, api_key):
    url = "https://image.novelai.net/ai/generate-image"

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "input": prompt,
        "model": "nai-diffusion-3",
        "action": "generate",
        "parameters": {
            "params_version": 3,
            "width": 832,
            "height": 1216,
            "scale": 7,
            "sampler": "k_dpmpp_2s_ancestral",
            "steps": 28,
            "n_samples": 1,
            "ucPreset": 3,
            "qualityToggle": False,
            "sm": False,
            "sm_dyn": False,
            "dynamic_thresholding": False,
            "controlnet_strength": 1,
            "legacy": False,
            "add_original_image": True,
            "cfg_rescale": 0,
            "noise_schedule": "karras",
            "legacy_v3_extend": False,
            "skip_cfg_above_sigma": None,
            "seed": random.randint(0, 4294967295),  # Random seed
            "negative_prompt": "worst quality, low quality, bad image, displeasing, [abstract], bad anatomy, very displeasing, extra, unfocused, jpeg artifacts, unfinished, chromatic aberration,",
            "reference_image_multiple": [],
            "reference_information_extracted_multiple": [],
            "reference_strength_multiple": []
        }
    }

    print("Sending request to NovelAI...")
    response = requests.post(url, json=payload, headers=headers)

    if response.status_code != 200:
        print(f"Failed to generate image. Status code: {response.status_code}")
        print("Response Headers:", response.headers)
        print("Response Body:", response.text)
        return None

    print("Image generated successfully.")
    return response.content


def save_image(image_data, output_folder="output"):
    os.makedirs(output_folder, exist_ok=True)

    # Save the zip file in memory
    zip_path = os.path.join(output_folder, "output_image.zip")
    with open(zip_path, "wb") as f:
        f.write(image_data)
    print(f"Saved image as {zip_path}")

    # Extract the image from the zip file using BytesIO
    with zipfile.ZipFile(BytesIO(image_data), 'r') as zip_ref:
        zip_ref.extractall(output_folder)

    extracted_image_path = os.path.join(output_folder, "image_0.png")
    if os.path.exists(extracted_image_path):
        print(f"Extracted image saved as {extracted_image_path}")
    else:
        print("Warning: Could not find extracted image.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        prompt = sys.argv[1]
        image_data = generate_image(prompt, api_token)
        if image_data:
            save_image(image_data)
    else:
        print("Please provide a prompt as a command-line argument.")
