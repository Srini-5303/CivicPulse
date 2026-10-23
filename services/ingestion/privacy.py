from cryptography.fernet import Fernet

from libs.common.config import settings
from libs.common.pii import scrub
from services.ingestion.mappers import Protect


def make_protect() -> Protect:
    fernet = Fernet(settings.pii_key)

    def protect(text: str) -> tuple[str, str]:
        return fernet.encrypt(text.encode()).decode(), scrub(text)

    return protect
