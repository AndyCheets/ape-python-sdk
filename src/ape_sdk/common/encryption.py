import base64
from typing import Protocol


class SecretEncryptionProvider(Protocol):
    def encrypt(self, value: str) -> str:
        ...

    def decrypt(self, value: str) -> str:
        ...


class DevelopmentPlaceholderEncryptionProvider:
    """Development-only reversible obfuscation.

    TODO_TEMPLATE: Replace this with authenticated encryption backed by managed keys if this
    template worker stores secrets.
    This is not secure encryption.
    """

    prefix = "dev-placeholder:"

    def encrypt(self, value: str) -> str:
        encoded = base64.urlsafe_b64encode(value[::-1].encode("utf-8")).decode("ascii")
        return f"{self.prefix}{encoded}"

    def decrypt(self, value: str) -> str:
        if not value.startswith(self.prefix):
            return value
        encoded = value.removeprefix(self.prefix)
        return base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")[::-1]


def get_secret_encryption_provider() -> SecretEncryptionProvider:
    return DevelopmentPlaceholderEncryptionProvider()
