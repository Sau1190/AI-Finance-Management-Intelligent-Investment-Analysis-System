"""User-safe application errors. Do not put filesystem paths or stack traces here."""


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)

    def to_detail(self) -> dict:
        return {"code": self.code, "message": self.message}


class FileIntakeError(AppError):
    """Raised when an upload is rejected or cannot be stored."""


class ProcessingRequestError(AppError):
    """Raised when a processing request itself is invalid (wrong file type,
    file not found, etc). Distinct from a processing *run* failing, which is
    a normal outcome recorded on the ProcessingResult, not an exception.
    """


class ExtractionRequestError(AppError):
    """Raised when a PDF extraction request itself is invalid (wrong file
    type, file not found, etc). Distinct from an extraction *run* failing
    (corrupt/encrypted PDF), which is a normal outcome recorded on the
    PdfExtractionResult, not an exception.
    """


class AnalysisRequestError(AppError):
    """Raised when a fundamental-analysis request itself is invalid (wrong
    file type, no processing result to analyze, etc). Distinct from an
    analysis *run* failing (processing failed, storage failed), which is a
    normal outcome recorded on the FundamentalAnalysisResult, not an exception.
    """


class MarketDataRequestError(AppError):
    """Raised when a market-data request itself is invalid (bad symbol, no
    stored data to return, etc). Distinct from a provider *fetch* failing
    (rate limit, unreachable, unknown symbol), which is a normal outcome
    recorded on the MarketDataSnapshot, not an exception.
    """
