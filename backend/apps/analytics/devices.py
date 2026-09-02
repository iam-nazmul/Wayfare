import re

#: Coarse buckets. The funnel asks "does checkout work on phones", not which phone.
_TABLET = re.compile(r"ipad|tablet|playbook|silk|(android(?!.*mobile))", re.I)
_MOBILE = re.compile(r"android.*mobile|iphone|ipod|windows phone|blackberry|opera mini", re.I)
_BOT = re.compile(r"bot|crawler|spider|crawling|headless|lighthouse|pingdom", re.I)


def device_type(user_agent: str) -> str:
    """Bucket a user agent into bot / mobile / tablet / desktop.

    Deliberately crude and dependency-free: a full UA database would be a supply-chain risk for
    a field nobody segments below this granularity.
    """
    if not user_agent:
        return "unknown"
    if _BOT.search(user_agent):
        return "bot"
    if _MOBILE.search(user_agent):
        return "mobile"
    if _TABLET.search(user_agent):
        return "tablet"
    return "desktop"
