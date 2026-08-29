def describe_user_agent(user_agent: str | None) -> str:
    """A short, human-readable "Browser on OS" label for the sessions list
    -- no dependency pulled in for this (the app has stayed on a
    zero-subdependency-when-possible diet, see MessageContent.tsx's
    markdown-to-jsx choice), just substring checks against the handful of
    tokens that actually distinguish the browsers/platforms this app's
    users run. Order matters: Electron and Edge both also contain
    "Chrome/", and Chrome-on-iOS/Safari-on-iOS both contain "Safari/", so
    the more specific token has to be checked first.
    """
    if not user_agent:
        return "Unknown device"

    if "Electron/" in user_agent:
        browser = "DS Chat Desktop"
    elif "Edg/" in user_agent:
        browser = "Edge"
    elif "OPR/" in user_agent:
        browser = "Opera"
    elif "Firefox/" in user_agent:
        browser = "Firefox"
    elif "Chrome/" in user_agent:
        browser = "Chrome"
    elif "CriOS/" in user_agent:
        browser = "Chrome"
    elif "Safari/" in user_agent:
        browser = "Safari"
    else:
        browser = "Unknown browser"

    if "Windows" in user_agent:
        os_name = "Windows"
    elif "Mac OS X" in user_agent and ("iPhone" in user_agent or "iPad" in user_agent):
        os_name = "iOS"
    elif "Mac OS X" in user_agent:
        os_name = "macOS"
    elif "Android" in user_agent:
        os_name = "Android"
    elif "Linux" in user_agent:
        os_name = "Linux"
    else:
        os_name = "Unknown OS"

    if browser == "DS Chat Desktop":
        return f"{browser} ({os_name})"
    return f"{browser} on {os_name}"
