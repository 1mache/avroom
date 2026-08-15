from __future__ import annotations

import logging
from collections.abc import Sequence

from .checks import FileSizeCheck, FormatMimeCheck, TechnicalCheck, build_validation_context, default_technical_checks
from .types import ImageValidationError, TechnicalCheckResult

logger = logging.getLogger(__name__)


class ImageValidator:
    """Run deterministic technical checks on uploaded image bytes."""

    def __init__(self, checks: Sequence[TechnicalCheck] | None = None) -> None:
        self._checks = tuple(checks) if checks is not None else default_technical_checks()

    def validate(
        self,
        file_bytes: bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> list[TechnicalCheckResult]:
        """Validate upload bytes; raise :class:`ImageValidationError` on first failure."""
        results = self._run_checks(
            file_bytes, filename=filename, content_type=content_type, stop_on_first_failure=True
        )
        logger.info("Technical validation passed: checks=%d", len(results))
        return results

    def validate_all(
        self,
        file_bytes: bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> list[TechnicalCheckResult]:
        """Run every technical check and return all results; never raises for a failed check.

        Unlike :meth:`validate`, this does not stop at the first failure — it
        exists for debug/inspection tooling that wants the full scoreboard, not
        the production fail-fast gate. A decode failure is still terminal
        (every check past ``format_mime`` reads from the decoded context), but
        every check up to that point still gets a result.
        """
        results = self._run_checks(
            file_bytes, filename=filename, content_type=content_type, stop_on_first_failure=False
        )
        logger.info(
            "Technical validation (full report): checks=%d failed=%d",
            len(results),
            sum(1 for r in results if not r.passed),
        )
        return results

    def _run_checks(
        self,
        file_bytes: bytes,
        *,
        filename: str | None,
        content_type: str | None,
        stop_on_first_failure: bool,
    ) -> list[TechnicalCheckResult]:
        logger.info(
            "Technical validation starting: bytes=%d filename=%s content_type=%s stop_on_first_failure=%s",
            len(file_bytes),
            filename,
            content_type,
            stop_on_first_failure,
        )
        results: list[TechnicalCheckResult] = []

        file_size_check = FileSizeCheck()
        size_result = file_size_check.run_bytes(file_bytes)
        results.append(size_result)
        if not size_result.passed and stop_on_first_failure:
            raise ImageValidationError(results)

        format_check = FormatMimeCheck()
        format_result = format_check.run_bytes(file_bytes, content_type=content_type)
        results.append(format_result)
        if not format_result.passed and stop_on_first_failure:
            raise ImageValidationError(results)

        try:
            ctx = build_validation_context(file_bytes, filename=filename, content_type=content_type)
        except ValueError as exc:
            decode_result = TechnicalCheckResult(
                name="decode",
                passed=False,
                message=str(exc),
            )
            results.append(decode_result)
            if stop_on_first_failure:
                raise ImageValidationError(results) from exc
            # Remaining checks all read from the decoded context — nothing
            # more can be reported.
            return results

        # Both already ran above, on raw bytes, before the decode that the
        # remaining checks need.
        already_run = {FileSizeCheck.name, FormatMimeCheck.name}
        for check in self._checks:
            if check.name in already_run:
                continue
            result = check.run(ctx)
            results.append(result)
            logger.debug(
                "Technical check finished: name=%s passed=%s score=%s",
                result.name,
                result.passed,
                result.score,
            )
            if not result.passed:
                logger.warning(
                    "Technical validation failed: name=%s message=%s",
                    result.name,
                    result.message,
                )
                if stop_on_first_failure:
                    raise ImageValidationError(results)
        return results
