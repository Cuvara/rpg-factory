"""Generate the committed tiny real-image fixtures used without Pillow."""
import sys
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parent / 'fixtures' / 'art2d'
root.mkdir(parents=True, exist_ok=True)
images = {
    'rgba.png': (Image.new('RGBA', (16, 8), (255, 0, 0, 0)), {}),
    'rgb.jpg': (Image.new('RGB', (16, 8), (255, 0, 0)), {'quality': 90}),
    'lossy.webp': (Image.new('RGB', (16, 8), (255, 0, 0)), {'quality': 80, 'lossless': False}),
    'lossless.webp': (Image.new('RGB', (16, 8), (255, 0, 0)), {'lossless': True}),
    'alpha.webp': (Image.new('RGBA', (16, 8), (255, 0, 0, 0)), {'lossless': True}),
    'odd.png': (Image.new('RGBA', (15, 8), (255, 0, 0, 0)), {}),
}
for name, (image, options) in images.items():
    image.save(root / name, **options)

if __name__ == '__main__':
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, 'reconfigure'):
            _stream.reconfigure(encoding='utf-8', errors='replace')
