"""Local Tesseract adapter. Only trusted host configuration may select binaries."""
from dataclasses import asdict, dataclass
from hashlib import sha256
from io import BytesIO
import json
import importlib.metadata
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic
import warnings

from lukart_work.domain.models import VersionPin

MAX_PAGES = 20
MAX_PIXELS = 20_000_000
MAX_TEXT_BYTES = 400_000


@dataclass(frozen=True)
class OCRConfig:
    tesseract: str
    tessdata: str
    pdftoppm: str

    def pin(self):
        # Include the actual Polish model and rasterizer, not asserted versions.
        paths = (Path(self.tesseract), Path(self.tessdata) / 'pol.traineddata', Path(self.pdftoppm))
        if any(not p.is_absolute() or not p.is_file() for p in paths):
            raise ValueError('OCR_CONFIGURATION_REQUIRED')
        identity = {name: sha256(path.read_bytes()).hexdigest()
                    for name, path in zip(('tesseract', 'pol', 'pdftoppm'), paths)}
        distribution = importlib.metadata.distribution('Pillow')
        if distribution.version != '12.3.0':
            raise ValueError('OCR_PILLOW_VERSION_MISMATCH')
        identity['pillow_version'] = distribution.version
        # Bind decoder/preprocessing code and bundled native libraries too.
        if not distribution.files:
            raise ValueError('OCR_PILLOW_PROVENANCE_REQUIRED')
        for name in sorted(distribution.files, key=str):
            normalized = str(name).replace('\\', '/')
            if (normalized.lower().startswith('pillow.libs/') or
                    normalized.startswith('PIL/') and
                    (normalized.endswith(('.py', '.pyd', '.dll', '.so', '.dylib')) or '.so.' in normalized)):
                path = distribution.locate_file(name)
                identity['pillow/' + normalized] = sha256(path.read_bytes().replace(b'\r\n', b'\n')
                    if normalized.endswith('.py') else path.read_bytes()).hexdigest()
        return VersionPin(id='tesseract-pol-local', version='1.0.0',
                          content_hash=sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest())

    def payload(self):
        return asdict(self)


class LocalOCR:
    def __init__(self, config):
        self.config = config
        self.pin = config.pin()
        self.deadline = monotonic() + 40

    def _run(self, args):
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise ValueError('OCR_TIMEOUT')
        subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=min(10, remaining), check=True)

    def _text(self, image, folder):
        output = Path(folder) / 'recognized'
        self._run([self.config.tesseract, str(image), str(output), '--tessdata-dir',
                   self.config.tessdata, '-l', 'pol', '--psm', '3'])
        with output.with_suffix('.txt').open('rb') as stream:
            raw = stream.read(MAX_TEXT_BYTES + 1)
        if len(raw) > MAX_TEXT_BYTES:
            raise ValueError('OCR_TEXT_LIMIT')
        return raw.decode('utf-8', errors='strict')

    @staticmethod
    def _check_image(image):
        if image.width <= 0 or image.height <= 0 or image.width * image.height > MAX_PIXELS:
            raise ValueError('OCR_PIXEL_LIMIT')

    def image(self, data):
        from PIL import Image
        rows = []
        with warnings.catch_warnings(), TemporaryDirectory(prefix='lukart-ocr-') as folder:
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                frames = getattr(image, 'n_frames', 1)
                if image.format not in ('PNG', 'JPEG', 'TIFF') or frames > MAX_PAGES:
                    raise ValueError('OCR_IMAGE_LIMIT')
                for page in range(frames):
                    image.seek(page)
                    self._check_image(image)
                    target = Path(folder) / 'page.png'
                    image.convert('RGB').save(target)
                    rows.append(('PAGE', str(page + 1), self._text(target, folder)))
        return rows

    def pdf_page(self, data, number, page):
        # Rasterize only the requested page at a bounded resolution and size.
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        if not (0 < width <= 10000 and 0 < height <= 10000) or width * height * (150 / 72) ** 2 > MAX_PIXELS:
            raise ValueError('OCR_PIXEL_LIMIT')
        with TemporaryDirectory(prefix='lukart-ocr-') as folder:
            source = Path(folder) / 'source.pdf'
            source.write_bytes(data)
            prefix = Path(folder) / 'page'
            self._run([self.config.pdftoppm, '-f', str(number), '-l', str(number),
                       '-singlefile', '-r', '150', '-png', str(source), str(prefix)])
            return self._text(prefix.with_suffix('.png'), folder)
