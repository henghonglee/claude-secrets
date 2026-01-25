"""Generate app icon for MCP Secrets."""

import subprocess
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Installing Pillow...")
    subprocess.run(["pip", "install", "pillow"], check=True)
    from PIL import Image, ImageDraw


def create_icon():
    """Create a simple lock icon for the app."""
    sizes = [16, 32, 64, 128, 256, 512, 1024]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        iconset = tmpdir / "AppIcon.iconset"
        iconset.mkdir()

        for size in sizes:
            # Create image
            img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Draw circular background
            padding = size // 10
            # Dark blue background
            draw.ellipse(
                [padding, padding, size - padding, size - padding],
                fill=(45, 85, 155, 255)
            )

            # Inner lighter circle for depth
            inner_padding = padding + size // 20
            draw.ellipse(
                [inner_padding, inner_padding, size - inner_padding, size - inner_padding],
                fill=(55, 100, 175, 255)
            )

            # Lock body dimensions
            lock_width = size * 0.4
            lock_height = size * 0.28
            lock_x = (size - lock_width) / 2
            lock_y = size * 0.48

            # Lock body (white rectangle)
            draw.rounded_rectangle(
                [lock_x, lock_y, lock_x + lock_width, lock_y + lock_height],
                radius=size // 30,
                fill=(255, 255, 255, 255)
            )

            # Lock shackle
            shackle_width = lock_width * 0.55
            shackle_height = size * 0.18
            shackle_x = (size - shackle_width) / 2
            shackle_y = lock_y - shackle_height + size * 0.02
            stroke_width = max(2, size // 16)

            # Draw shackle as thick arc
            draw.arc(
                [shackle_x, shackle_y, shackle_x + shackle_width, shackle_y + shackle_height * 1.5],
                start=180,
                end=0,
                fill=(255, 255, 255, 255),
                width=stroke_width
            )

            # Vertical lines of shackle
            line_bottom = lock_y + size * 0.02
            draw.line(
                [shackle_x + stroke_width // 2, shackle_y + shackle_height * 0.75,
                 shackle_x + stroke_width // 2, line_bottom],
                fill=(255, 255, 255, 255),
                width=stroke_width
            )
            draw.line(
                [shackle_x + shackle_width - stroke_width // 2, shackle_y + shackle_height * 0.75,
                 shackle_x + shackle_width - stroke_width // 2, line_bottom],
                fill=(255, 255, 255, 255),
                width=stroke_width
            )

            # Keyhole circle
            keyhole_radius = max(2, size * 0.05)
            keyhole_x = size / 2
            keyhole_y = lock_y + lock_height * 0.38
            draw.ellipse(
                [keyhole_x - keyhole_radius, keyhole_y - keyhole_radius,
                 keyhole_x + keyhole_radius, keyhole_y + keyhole_radius],
                fill=(45, 85, 155, 255)
            )

            # Keyhole bottom (small rectangle)
            key_rect_width = keyhole_radius * 0.8
            key_rect_height = lock_height * 0.3
            draw.rectangle(
                [keyhole_x - key_rect_width / 2, keyhole_y,
                 keyhole_x + key_rect_width / 2, keyhole_y + key_rect_height],
                fill=(45, 85, 155, 255)
            )

            # Save regular and @2x versions
            img.save(iconset / f"icon_{size}x{size}.png")
            if size <= 512:
                # Create @2x version at double size
                img.save(iconset / f"icon_{size}x{size}@2x.png")

        # For @2x versions, we need the correct naming
        # icon_16x16@2x.png should be 32x32 pixels
        # Let's regenerate with correct sizes
        for base_size in [16, 32, 128, 256, 512]:
            double_size = base_size * 2
            if double_size <= 1024:
                # Read the larger size image and save as @2x
                large_img = Image.open(iconset / f"icon_{double_size}x{double_size}.png")
                large_img.save(iconset / f"icon_{base_size}x{base_size}@2x.png")

        # Convert to icns using iconutil
        result = subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", "app_icon.icns"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"iconutil error: {result.stderr}")
            # List what files we have
            print("Generated files:")
            for f in sorted(iconset.iterdir()):
                img = Image.open(f)
                print(f"  {f.name}: {img.size}")
            raise Exception("Failed to create icns")

    print("Created app_icon.icns")


if __name__ == "__main__":
    create_icon()
