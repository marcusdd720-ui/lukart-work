"""Private isolated parser entrypoint; stdout is a bounded machine result only."""
import base64
import json
import logging
import sys
from .extract import extract
from .models import ExtractionBody


def main():
    logging.disable(logging.CRITICAL)
    try:
        if sys.platform != 'win32':
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_CPU, (10, 30))
        payload = json.loads(sys.stdin.buffer.read(24 * 1024 * 1024 + 1))
        data = base64.b64decode(payload['data'], validate=True)
        if len(data) > 16 * 1024 * 1024:
            raise ValueError('INPUT_LIMIT')
        from .ocr import OCRConfig
        config = OCRConfig(**payload['ocr']) if payload.get('ocr') is not None else None
        if sys.platform != 'win32':
            cpu = 30 if config is not None else 10
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        result = extract(data, payload['media_type'], config)
        output = result.model_dump_json().encode()
        if len(output) > 8 * 1024 * 1024:
            raise ValueError('OUTPUT_LIMIT')
    except Exception:
        output = ExtractionBody(media_type='application/octet-stream', classification='UNKNOWN', status='FAILED',
            fragments=(), candidates=(), warnings=('UNTRUSTED_SOURCE', 'REVIEW_REQUIRED', 'PARSER_REJECTED')).model_dump_json().encode()
    sys.stdout.buffer.write(output)


if __name__ == '__main__':
    main()
