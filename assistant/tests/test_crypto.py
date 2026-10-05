from django.test import SimpleTestCase

from assistant.crypto import SecretDecryptionError, decrypt_secret, encrypt_token


class CryptoTests(SimpleTestCase):
    def test_roundtrip(self):
        cipher = encrypt_token("super-secret")
        self.assertNotEqual(cipher, "super-secret")
        self.assertEqual(decrypt_secret(cipher), "super-secret")

    def test_bad_cipher_raises(self):
        with self.assertRaises(SecretDecryptionError):
            decrypt_secret("not-a-valid-fernet-token")
