# Cert.py
"""Модуль для генерации самоподписанных сертификатов Mumble"""

import os
import datetime
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


def GenerateMumbleCert(username: str, cert_path: str, key_path: str, days_valid: int = 3650) -> bool:
    """
    Генерирует самоподписанный сертификат для Mumble.
    ⚠️ ВСЕГДА создаёт новый сертификат (перезаписывает существующие).
    
    Returns:
        bool: True если успешно, False если ошибка
    """
    # ✅ НЕТ ПРОВЕРКИ — генерируем ВСЕГДА заново!
    print(f"🔐 Генерация НОВОГО рандомного сертификата для '{username}'...")
    
    try:
        # Генерация приватного ключа (RSA 2048 бит) — всегда новый!
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # Данные субъекта
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, username),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MumbleBot"),
        ])
        
        # Создание сертификата
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())  # ← Случайный серийный номер
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=days_valid))
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .sign(private_key, hashes.SHA256(), default_backend())
        )
        
        # Сохранение ключа (без пароля)
        with open(key_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        # Сохранение сертификата
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        
        # Права доступа (для Linux)
        try:
            os.chmod(key_path, 0o600)
        except:
            pass
        
        print(f"✅ Сертификат: {cert_path}")
        print(f"✅ Ключ: {key_path}")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка генерации: {e}")
        return False