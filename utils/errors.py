class ApiError(Exception):
    pass


class SubredditNotFound(ApiError):
    def __init__(self, *args):
        super().__init__(*args)


class SortError(ApiError):
    def __init__(self, *args):
        super().__init__(*args)


class CountryNotFound(ApiError):
    def __init__(self, *args):
        super().__init__(*args)
