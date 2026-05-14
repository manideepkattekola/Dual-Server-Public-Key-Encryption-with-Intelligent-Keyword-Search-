import hashlib
import secrets


def _sha256_hex(*parts):
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DualServerPEKS:
    """DS-PEKS simulation with explicit Front-Server and Back-Server flow."""

    def __init__(self):
        self.front_server = None
        self.back_server = None

    def set_servers(self, front_server, back_server):
        self.front_server = front_server
        self.back_server = back_server

    @staticmethod
    def _normalize_keyword(keyword):
        return (keyword or "").strip().lower()

    def generate_peks_ciphertext(self, keyword):
        if not self.front_server or not self.back_server:
            raise ValueError("Front and Back servers must be configured before encryption")

        normalized = self._normalize_keyword(keyword)
        keyword_hash = _sha256_hex("KW", normalized)
        nonce = secrets.token_hex(16)

        fs_tag = _sha256_hex("FS-TAG", keyword_hash, self.front_server.public_key)
        bs_tag = _sha256_hex("BS-TAG", keyword_hash, self.back_server.public_key)

        c1 = nonce
        c2 = _sha256_hex("C2", fs_tag, c1)
        c3 = _sha256_hex("C3", bs_tag, c1)
        return c1, c2, c3

    def generate_trapdoor(self, keyword):
        if not self.front_server or not self.back_server:
            raise ValueError("Front and Back servers must be configured before trapdoor generation")

        normalized = self._normalize_keyword(keyword)
        keyword_hash = _sha256_hex("KW", normalized)

        trapdoor_fs = _sha256_hex("FS-TAG", keyword_hash, self.front_server.public_key)
        trapdoor_bs = _sha256_hex("BS-TAG", keyword_hash, self.back_server.public_key)
        return trapdoor_fs, trapdoor_bs


class FrontServer:
    """Front Server simulation for DS-PEKS."""

    def __init__(self):
        self.secret_key = None
        self.public_key = None

    def setup_keys(self):
        self.secret_key = secrets.token_hex(32)
        self.public_key = _sha256_hex("PK-FS", self.secret_key)

    def front_test(self, sk_fs, ciphertext, trapdoor):
        c1, c2, c3 = ciphertext
        trapdoor_fs, trapdoor_bs = trapdoor

        expected_c2 = _sha256_hex("C2", trapdoor_fs, c1)
        if expected_c2 != c2:
            return None

        fs_proof = _sha256_hex("FS-PROOF", sk_fs, c1, c2, trapdoor_fs)
        return {
            "c1": c1,
            "c3": c3,
            "trapdoor_bs": trapdoor_bs,
            "fs_proof": fs_proof,
        }


class BackServer:
    """Back Server simulation for DS-PEKS."""

    def __init__(self):
        self.secret_key = None
        self.public_key = None

    def setup_keys(self):
        self.secret_key = secrets.token_hex(32)
        self.public_key = _sha256_hex("PK-BS", self.secret_key)

    def back_test(self, sk_bs, cits):
        c1 = cits.get("c1", "")
        c3 = cits.get("c3", "")
        trapdoor_bs = cits.get("trapdoor_bs", "")

        expected_c3 = _sha256_hex("C3", trapdoor_bs, c1)
        if expected_c3 != c3:
            return 0

        _ = _sha256_hex("BS-PROOF", sk_bs, c1, c3)
        return 1
