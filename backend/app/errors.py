"""Errors that become HTTP answers. The message tells the user what to do next and never shows internals."""


class ApiError(Exception):
    status_code = 400

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class BadRequest(ApiError):       # 400: the request itself is wrong (bad file type, missing field)
    status_code = 400


class Unauthorized(ApiError):     # 401: not logged in
    status_code = 401


class Forbidden(ApiError):        # 403: logged in, but this role may not do this
    status_code = 403


class NotFound(ApiError):         # 404: does not exist, or is not yours
    status_code = 404


class Conflict(ApiError):         # 409: the case is in the wrong state for this action
    status_code = 409
