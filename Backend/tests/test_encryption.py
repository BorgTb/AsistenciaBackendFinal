import json
import pytest
from encryption import cifrar_embedding, descifrar_embedding


class TestEncryption:
    """Tests unitarios para cifrado AES de embeddings biometricos."""

    def test_cifrar_produce_string_valido(self):
        result = cifrar_embedding([0.1, 0.2, 0.3])
        assert isinstance(result, str)
        assert len(result) > 10

    def test_roundtrip_small_embedding(self):
        embedding = [0.1, -0.2, 0.3, 0.0]
        encrypted = cifrar_embedding(embedding)
        decrypted = descifrar_embedding(encrypted)
        assert decrypted == embedding

    def test_roundtrip_128_dim_embedding(self):
        embedding = [float(i % 13) / 7.0 for i in range(128)]
        encrypted = cifrar_embedding(embedding)
        decrypted = descifrar_embedding(encrypted)
        assert decrypted == embedding
        assert len(decrypted) == 128

    def test_descifrar_retorna_none_para_valores_vacios(self):
        assert descifrar_embedding(None) is None
        assert descifrar_embedding('') is None

    def test_cifrados_diferentes_mismo_embedding_iv_distinto(self):
        embedding = [1.0, 2.0, 3.0]
        c1 = cifrar_embedding(embedding)
        c2 = cifrar_embedding(embedding)
        c3 = cifrar_embedding(embedding)
        assert c1 != c2 != c3

    def test_cada_cifrado_produce_roundtrip_correcto(self):
        for i in range(20):
            embedding = [float(j) for j in range(i, i + 3)]
            encrypted = cifrar_embedding(embedding)
            assert descifrar_embedding(encrypted) == embedding

    def test_embedding_con_ceros(self):
        embedding = [0.0] * 64
        encrypted = cifrar_embedding(embedding)
        assert descifrar_embedding(encrypted) == embedding

    def test_embedding_con_negativos(self):
        embedding = [-0.5] * 32
        encrypted = cifrar_embedding(embedding)
        assert descifrar_embedding(encrypted) == embedding

    def test_tampered_ciphertext_falla(self):
        embedding = [0.5] * 10
        encrypted = cifrar_embedding(embedding)
        tampered = encrypted[:-5] + 'XXXXX'
        with pytest.raises((ValueError, json.JSONDecodeError)):
            descifrar_embedding(tampered)

    def test_fallback_json_plano_legacy(self):
        old_format = json.dumps([1.0, 2.0, 3.0])
        result = descifrar_embedding(old_format)
        assert result == [1.0, 2.0, 3.0]
