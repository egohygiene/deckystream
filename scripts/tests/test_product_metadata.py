"""Primary names and bounded legacy aliases share one checked source contract."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("product_generator", ROOT / "scripts/generate-product.py")
PRODUCT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PRODUCT)


class ProductMetadataTests(unittest.TestCase):
    def test_generated_names_keep_primary_and_legacy_identities_distinct(self):
        outputs = PRODUCT.outputs()
        python = {}
        exec(compile(outputs[ROOT / "steamdeck/product.py"], "generated-product", "exec"), python)
        self.assertEqual((python["CLI_NAME"], python["PLUGIN_ID"], python["STORAGE_NAMESPACE"]),
                         ("deckystream", "deckystream", "deckystream"))
        self.assertEqual((python["LEGACY_CLI_NAME"], python["LEGACY_PLUGIN_ID"], python["LEGACY_STORAGE_NAMESPACE"]),
                         ("obsgod", "OBSGod", "obsgod"))
        self.assertEqual((python["ENV_PREFIX"], python["LEGACY_ENV_PREFIX"]), ("DECKYSTREAM", "OBSGOD"))
        for path, content in outputs.items():
            self.assertEqual(path.read_text(), content, "Generated identity projection drift")

    def test_unknown_primary_or_legacy_data_names_cannot_be_generated(self):
        original = json.loads((ROOT / "product.json").read_text())
        for field in ("compatibility", "legacy_compatibility"):
            value = json.loads(json.dumps(original))
            value[field]["storage_namespace"] = "unrelated-user-data"
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "product.json").write_text(json.dumps(value))
                with patch.object(PRODUCT, "ROOT", root), self.assertRaisesRegex(ValueError, "migration contract|Legacy migration"):
                    PRODUCT.outputs()


if __name__ == "__main__":
    unittest.main()
