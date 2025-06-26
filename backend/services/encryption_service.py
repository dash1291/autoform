import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EncryptionService:
    """Service for encrypting and decrypting sensitive data"""

    def __init__(self):
        # Get encryption key from environment or generate a consistent one
        self.encryption_key = self._get_or_create_key()
        self.cipher_suite = Fernet(self.encryption_key)

    def _get_or_create_key(self) -> bytes:
        """Get encryption key from environment or derive from secret"""
        # Try to get key from environment
        key_str = os.getenv("ENCRYPTION_KEY")
        if key_str:
            # ENCRYPTION_KEY should be a base64-encoded Fernet key
            # Return it as bytes (Fernet expects the base64-encoded key as bytes)
            return key_str.encode()

        # Otherwise, derive key from a secret
        secret = os.getenv("SECRET_KEY_BASE", "default-secret-key-change-this")
        salt = b"autoform-team-aws-config"  # Static salt for consistent key derivation

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
        return key

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string and return base64 encoded ciphertext"""
        if not plaintext:
            return ""

        encrypted = self.cipher_suite.encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(encrypted).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt base64 encoded ciphertext and return plaintext"""
        if not ciphertext:
            return ""

        try:
            decoded = base64.urlsafe_b64decode(ciphertext.encode())
            decrypted = self.cipher_suite.decrypt(decoded)
            return decrypted.decode()
        except Exception:
            # If decryption fails, return empty string
            # This handles cases where the encryption key has changed
            return ""


# Singleton instance
encryption_service = EncryptionService()
