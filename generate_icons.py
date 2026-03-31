import os
from PIL import Image

app_icon_dir = r"e:\ns\frontend\nsapp\ios\Runner\Assets.xcassets\AppIcon.appiconset"
source_image = os.path.join(app_icon_dir, "1024.png")

sizes = {
    "152.png": (152, 152),
    "167.png": (167, 167),
    "76.png": (76, 76),
    "167_ipad.png": (167, 167), # Duplicate for convenience
}

if not os.path.exists(source_image):
    print(f"Error: Source image {source_image} not found.")
else:
    with Image.open(source_image) as img:
        for name, size in sizes.items():
            out_path = os.path.join(app_icon_dir, name)
            img.resize(size, Image.Resampling.LANCZOS).convert("RGBA").save(out_path)
            print(f"Generated {out_path}")
