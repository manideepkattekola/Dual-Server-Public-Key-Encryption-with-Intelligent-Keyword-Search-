from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad, unpad
import os
import base64
import hashlib
import json

class CryptoUtils:
    """Utility class for cryptographic operations"""

    def __init__(self, master_secret=None):
        secret = master_secret or os.getenv("APP_MASTER_KEY", "ds-peks-demo-master-key")
        self.master_key = hashlib.sha256(secret.encode("utf-8")).digest()
    
    @staticmethod
    def generate_aes_key():
        """Generate random AES key"""
        return os.urandom(32)  # 256-bit key
    
    @staticmethod
    def generate_iv():
        """Generate random initialization vector"""
        return os.urandom(16)

    @staticmethod
    def iv_to_text(iv_bytes):
        return base64.b64encode(iv_bytes).decode("utf-8")

    @staticmethod
    def iv_from_text(iv_text):
        return base64.b64decode(iv_text.encode("utf-8"))
    
    @staticmethod
    def encrypt_file(input_path, output_path, key, iv):
        """Encrypt file using AES-CBC"""
        cipher = AES.new(key, AES.MODE_CBC, iv)
        
        with open(input_path, 'rb') as f:
            plaintext = f.read()
        
        ciphertext = cipher.encrypt(pad(plaintext, AES.block_size))
        
        with open(output_path, 'wb') as f:
            f.write(ciphertext)
    
    @staticmethod
    def decrypt_file(input_path, output_path, key, iv):
        """Decrypt file using AES-CBC"""
        cipher = AES.new(key, AES.MODE_CBC, iv)
        
        with open(input_path, 'rb') as f:
            ciphertext = f.read()
        
        plaintext = unpad(cipher.decrypt(ciphertext), AES.block_size)
        
        with open(output_path, 'wb') as f:
            f.write(plaintext)
    
    def encrypt_aes_key(self, aes_key):
        """Encrypt AES key using reversible XOR-based key wrapping for demo."""
        wrapped = bytes(aes_key[i] ^ self.master_key[i % len(self.master_key)] for i in range(len(aes_key)))
        return base64.b64encode(wrapped).decode("utf-8")

    def decrypt_aes_key(self, encrypted_key):
        wrapped = base64.b64decode(encrypted_key.encode("utf-8"))
        return bytes(wrapped[i] ^ self.master_key[i % len(self.master_key)] for i in range(len(wrapped)))

    def encrypt_keywords_metadata(self, keywords):
        """Encrypt selected keywords metadata for owner-only display."""
        payload = json.dumps(keywords, ensure_ascii=True).encode("utf-8")
        wrapped = bytes(payload[i] ^ self.master_key[i % len(self.master_key)] for i in range(len(payload)))
        return base64.b64encode(wrapped).decode("utf-8")

    def decrypt_keywords_metadata(self, encrypted_keywords):
        if not encrypted_keywords:
            return []

        wrapped = base64.b64decode(encrypted_keywords.encode("utf-8"))
        payload = bytes(wrapped[i] ^ self.master_key[i % len(self.master_key)] for i in range(len(wrapped)))
        try:
            value = json.loads(payload.decode("utf-8"))
            if isinstance(value, list):
                return value
        except Exception:
            return []
        return []