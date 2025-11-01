#!/usr/bin/env python3
"""
Generate Chinese seal-style favicon for QingDu
Creates a red seal with white "轻读" characters
"""

from PIL import Image, ImageDraw, ImageFont
import os
import sys

# Seal colors
SEAL_RED = "#CC0000"  # Traditional Chinese seal red
SEAL_WHITE = "#FFFFFF"  # White for characters
BORDER_WIDTH = 8  # Border width for the seal effect

def create_seal_favicon(text, size, font_size_ratio=0.5):
    """
    Create a Chinese seal-style square image

    Args:
        text: Chinese characters to display
        size: Size of the square image (width=height)
        font_size_ratio: Font size as ratio of image size
    """
    # Create image with red background
    img = Image.new('RGB', (size, size), SEAL_RED)
    draw = ImageDraw.Draw(img)

    # Try to use a Chinese font, fallback to default
    font_size = int(size * font_size_ratio)
    font = None

    # Try common Chinese font paths on Linux
    font_paths = [
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
        '/usr/share/fonts/truetype/arphic/uming.ttc',
        '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
    ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, font_size)
                print(f"Using font: {font_path}")
                break
            except Exception as e:
                print(f"Could not load font {font_path}: {e}")
                continue

    if font is None:
        print("Warning: Could not find Chinese font, using default font")
        font = ImageFont.load_default()

    # Draw inner border (seal frame effect)
    border = max(2, size // 32)
    draw.rectangle(
        [border, border, size-border, size-border],
        outline=SEAL_WHITE,
        width=max(1, border // 2)
    )

    # Calculate text position to center it
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (size - text_width) // 2
    y = (size - text_height) // 2 - bbox[1]

    # Draw the text in white
    draw.text((x, y), text, fill=SEAL_WHITE, font=font)

    return img

def generate_all_sizes(text="轻读", output_dir="../static"):
    """Generate all required favicon sizes"""

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    sizes = {
        'favicon-16x16.png': 16,
        'favicon-32x32.png': 32,
        'favicon-192x192.png': 192,
        'favicon-512x512.png': 512,
        'apple-touch-icon.png': 180,
    }

    images = []

    print(f"Generating favicons with text: {text}")
    print("-" * 50)

    # Generate PNG files
    for filename, size in sizes.items():
        print(f"Creating {filename} ({size}x{size})...")
        img = create_seal_favicon(text, size)
        filepath = os.path.join(output_dir, filename)
        img.save(filepath, 'PNG')
        print(f"  ✓ Saved: {filepath}")

        # Store for ICO generation
        if size in [16, 32, 48]:
            images.append(img)

    # Generate 48x48 for ICO (not saved as separate PNG)
    print("Creating 48x48 for ICO...")
    img_48 = create_seal_favicon(text, 48)
    images.insert(1, img_48)  # Insert between 16 and 32

    # Generate multi-resolution ICO file
    print("Creating favicon.ico (16x16, 32x32, 48x48)...")
    ico_path = os.path.join(output_dir, 'favicon.ico')
    images[0].save(
        ico_path,
        format='ICO',
        sizes=[(16, 16), (32, 32), (48, 48)]
    )
    print(f"  ✓ Saved: {ico_path}")

    # Generate site.webmanifest
    manifest_path = os.path.join(output_dir, 'site.webmanifest')
    manifest_content = """{
    "name": "QingDu",
    "short_name": "QingDu",
    "description": "HSK Chinese Text Analyzer",
    "icons": [
        {
            "src": "/static/favicon-192x192.png",
            "sizes": "192x192",
            "type": "image/png"
        },
        {
            "src": "/static/favicon-512x512.png",
            "sizes": "512x512",
            "type": "image/png"
        }
    ],
    "theme_color": "#CC0000",
    "background_color": "#FFFFFF",
    "display": "standalone"
}"""

    with open(manifest_path, 'w', encoding='utf-8') as f:
        f.write(manifest_content)
    print(f"  ✓ Saved: {manifest_path}")

    print("-" * 50)
    print("✅ All favicon files generated successfully!")
    print(f"\nGenerated files in {output_dir}:")
    print("  - favicon.ico (16x16, 32x32, 48x48)")
    print("  - favicon-16x16.png")
    print("  - favicon-32x32.png")
    print("  - favicon-192x192.png (Android)")
    print("  - favicon-512x512.png (Android)")
    print("  - apple-touch-icon.png (180x180)")
    print("  - site.webmanifest")

if __name__ == "__main__":
    # Get script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, "../static")

    # Allow custom text via command line
    text = sys.argv[1] if len(sys.argv) > 1 else "轻读"

    generate_all_sizes(text, output_dir)
