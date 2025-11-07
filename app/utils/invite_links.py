from urllib.parse import urlparse


def extract_link_code(invite_link: str) -> str:
    parsed = urlparse(invite_link)
    path = (parsed.path or "").strip("/")
    if not path:
        return invite_link
    return path.split("/")[-1]


__all__ = ["extract_link_code"]
