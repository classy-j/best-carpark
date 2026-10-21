"""Application-level exceptions. Kept dependency-free so every layer can import them."""


class ApiClientError(Exception):
    """An external API (OneMap / HDB / LTA) failed or returned something unusable."""


class NotFoundError(ApiClientError):
    """The external API worked, but had no result for the query."""


class AddressNotFoundError(NotFoundError):
    """OneMap could not geocode the destination address (UC-12 Invalid Destination Error)."""


class RouteNotFoundError(NotFoundError):
    """OneMap could not find a walking route between two points."""


class MultipleDestinationsError(Exception):
    """The destination matches several places; the Driver must pick one (UC-01 AF1)."""

    def __init__(self, matches):
        super().__init__(f"{len(matches)} places match the destination")
        self.matches = matches
