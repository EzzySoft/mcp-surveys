class SurveyError(Exception):
    """Base survey error."""


class SurveyNotFound(SurveyError):
    """Survey is missing or expired."""


class SurveyForbidden(SurveyError):
    """Result token is invalid."""


class SurveyLocked(SurveyError):
    """Survey cannot be edited after completion."""


class SurveyValidationError(SurveyError):
    """Survey payload or answer is invalid."""


class RateLimitExceeded(SurveyError):
    """Caller has created too many surveys in the current window."""
