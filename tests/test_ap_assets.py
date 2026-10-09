import unittest
from pathlib import Path
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1] / "app" / "ap_statements"
FRONTEND = ROOT / "frontend"

class AssetReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ("src", "href") and not value.startswith("data:"):
                self.references.append(value)

class APAssetTests(unittest.TestCase):
    def test_browser_entrypoint_has_local_existing_assets(self):
        index = FRONTEND / "index.html"
        self.assertTrue(index.is_file(), "AP component entrypoint must exist")
        parser = AssetReferences()
        parser.feed(index.read_text(encoding="utf-8"))
        self.assertTrue(parser.references)
        for ref in parser.references:
            with self.subTest(ref=ref):
                self.assertTrue(ref.startswith("./"), "component URLs must be relative")
                self.assertTrue((FRONTEND / ref).is_file())

    def test_pdf_and_ocr_runtime_is_packaged(self):
        for name in ("app.mjs", "core.mjs", "demo.mjs", "extraction.mjs",
                     "vendor/pdf.mjs", "vendor/pdf.worker.mjs",
                     "vendor/tesseract.min.js", "vendor/worker.min.js",
                     "vendor/eng.traineddata.gz", "bridge.bundle.mjs"):
            with self.subTest(name=name):
                file = FRONTEND / name
                self.assertTrue(file.is_file(), f"missing required runtime asset {name}")
                self.assertGreater(file.stat().st_size, 20)
        core = FRONTEND / "vendor" / "tesseract-core"
        self.assertTrue(any(p.with_suffix(".js").is_file() for p in core.glob("*.wasm")))

    def test_licenses_and_source_identity_are_included(self):
        self.assertTrue((ROOT / "THIRD_PARTY_NOTICES.md").is_file())
        for name in ("pdfjs-dist", "tesseract.js", "tesseract.js-core", "eng", "streamlit-component-lib"):
            self.assertTrue((FRONTEND / "vendor" / "licenses" / f"{name}.txt").is_file(), name)
        self.assertFalse((FRONTEND / ".openai").exists())

if __name__ == "__main__":
    unittest.main()
