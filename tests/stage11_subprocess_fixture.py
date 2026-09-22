"""Fresh-process determinism probe for Stage 11."""
import json

from lukart_work.rendering.service import RenderingEngine
from tests.stage11_render_fixture import build_fixture


request, records = build_fixture()
bundle = RenderingEngine().render(request, records)
print(json.dumps({
    "docx": bundle.meta.receipt.artifacts[0].content_hash,
    "pdf": bundle.meta.receipt.artifacts[1].content_hash,
    "semantic": bundle.meta.receipt.semantic_digest,
    "model": bundle.meta.receipt.render_model_digest,
    "layout": bundle.meta.receipt.layout_digest,
    "renderer": bundle.meta.receipt.renderer.content_hash,
    "profile": bundle.meta.receipt.render_profile.content_hash,
}, sort_keys=True))
