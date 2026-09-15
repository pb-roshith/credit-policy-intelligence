import unittest

from app.manufacture_data.policy_generation_service import (
    GENERATED_DOCUMENT_COUNT, IMPORTED_DOCUMENT_COUNT, POLICY_LIBRARY_DOCUMENT_COUNT,
    POLICY_SPECS,
)
from app.scripts.import_external_policies import EXTERNAL_POLICIES


class PolicyGenerationConfigurationTest(unittest.TestCase):
    def test_library_contains_25_generated_and_10_imported_files(self):
        self.assertEqual(GENERATED_DOCUMENT_COUNT, 25)
        self.assertEqual(IMPORTED_DOCUMENT_COUNT, 10)
        self.assertEqual(POLICY_LIBRARY_DOCUMENT_COUNT, 35)
        self.assertEqual(len(EXTERNAL_POLICIES), 10)

    def test_generated_filenames_have_no_clause_prefix(self):
        names = [f"{spec['name']}.pdf" for spec in POLICY_SPECS]
        self.assertEqual(len(names), len(set(names)))
        for spec, file_name in zip(POLICY_SPECS, names):
            self.assertFalse(file_name.startswith(f"{spec['clause']} "))

    def test_five_requested_policies_are_in_generation_set(self):
        expected = {
            "Credit Duration Risk Policy", "Credit Portfolio Liquidity Policy",
            "Credit Rating Standards", "Foreign Currency Credit Risk Policy",
            "Industry Risk Assessment Policy",
        }
        self.assertTrue(expected.issubset({spec["name"] for spec in POLICY_SPECS}))


if __name__ == "__main__":
    unittest.main()
