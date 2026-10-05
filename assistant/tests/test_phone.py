from django.test import SimpleTestCase

from assistant.phone import canonical_phone, mask_phone, phone_variants


class PhoneTests(SimpleTestCase):
    def test_canonical_forms(self):
        self.assertEqual(canonical_phone("03001234567"), "923001234567")
        self.assertEqual(canonical_phone("+92 300 1234567"), "923001234567")
        self.assertEqual(canonical_phone("00923001234567"), "923001234567")
        self.assertEqual(canonical_phone("923001234567"), "923001234567")
        self.assertEqual(canonical_phone("3001234567"), "923001234567")

    def test_variants_include_legacy(self):
        variants = phone_variants("923001234567")
        self.assertIn("923001234567", variants)
        self.assertIn("03001234567", variants)
        self.assertIn("3001234567", variants)

    def test_non_pk_untouched(self):
        self.assertEqual(canonical_phone("14155552671"), "14155552671")

    def test_mask(self):
        self.assertTrue(mask_phone("923001234567").endswith("4567"))
        self.assertIn("*", mask_phone("923001234567"))
