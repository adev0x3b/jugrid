"""The HTTP client every source is fetched with."""

import httpx

USER_AGENT = "JuGrid/0.1 (+https://github.com/adev0x3b/jugrid)"

# The largest file a source sends: a NEX-GDDP year is about 250 MB, a flood tile less.
# Anything bigger is refused before it fills the disk.
MAX_DOWNLOAD_BYTES = 2 * 1024**3


class InsecureRequest(httpx.RequestError):
    """A request, or a redirect, that would leave HTTPS."""


def _https_only(request: httpx.Request) -> None:
    if request.url.scheme != "https":
        raise InsecureRequest(
            f"refusing {request.url.scheme}://{request.url.host}: sources are fetched over HTTPS",
            request=request,
        )


def client() -> httpx.Client:
    """Follows redirects, but never to plain HTTP, where an answer could be tampered with."""
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        max_redirects=5,
        event_hooks={"request": [_https_only]},
    )


def check_size(response: httpx.Response, received: int) -> None:
    """Raise once a download is, or says it will be, larger than ``MAX_DOWNLOAD_BYTES``."""
    limit = MAX_DOWNLOAD_BYTES
    declared = response.headers.get("content-length", "")
    if (declared.isdigit() and int(declared) > limit) or received > limit:
        raise ValueError(f"{response.url} is larger than {limit} bytes")
