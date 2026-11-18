class ValidationError(Exception):
    def __init__(self, message):
        self.message = message


class HashFailure(Exception):
    pass
