"""Dependency-free helpers for the RAS demo event listener."""


def cper_download_uri(
        additional_data_uri: str | None,
        origin_of_condition: str | None) -> str | None:
    """Return an attachment URI only when an event identifies CPER data."""
    if additional_data_uri:
        return additional_data_uri
    if (origin_of_condition
            and "/LogServices/CPER/Entries/" in origin_of_condition):
        return f"{origin_of_condition.rstrip('/')}/Attachment"
    return None
