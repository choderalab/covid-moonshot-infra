from dataclasses import dataclass


class AnalysisError(RuntimeError):
    pass


class DataValidationError(AnalysisError):
    def __init__(self, message: str, path: str):
        super(message)
        self.path = path


class InsufficientDataError(AnalysisError):
    pass


class InvalidResultError(AnalysisError):
    pass