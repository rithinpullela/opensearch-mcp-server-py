# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Custom OpenSearch connection classes with enhanced functionality.

This module provides custom connection classes that extend the standard
OpenSearch connection classes with additional features like response size limiting.
"""

import logging
import time
from opensearchpy import AsyncHttpConnection


# Configure logging
logger = logging.getLogger(__name__)

# Constants
# Default maximum response size: 10 MiB. Protection is ON by default to prevent a
# very large OpenSearch response from exhausting process memory, and this matches
# the value documented in USER_GUIDE.md. Set OPENSEARCH_MAX_RESPONSE_SIZE (or the
# per-call override) to raise/lower it; the limit is enforced on the *decompressed*
# response bytes via incremental streaming (aborts before the whole body is buffered).
DEFAULT_MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10 MiB


# Base exception class (to avoid circular imports)
class OpenSearchClientError(Exception):
    """Base exception for OpenSearch client errors."""

    pass


class ResponseSizeExceededError(OpenSearchClientError):
    """Exception raised when response size exceeds the configured limit."""

    pass


def _log_request_event(
    method: str,
    endpoint: str,
    status_code: int | None,
    duration_ms: float,
    status: str,
    response_size: int | None = None,
    error: str | None = None,
) -> None:
    """Emit a structured log event for OpenSearch HTTP requests."""
    log_extra: dict[str, object] = {
        'event_type': 'opensearch_request',
        'http_method': method,
        'endpoint': endpoint,
        'status': status,
        'duration_ms': duration_ms,
    }
    if status_code is not None:
        log_extra['status_code'] = status_code
    if response_size is not None:
        log_extra['response_size'] = response_size
    if error:
        log_extra['error'] = error

    if status == 'success':
        logger.info(
            f'OpenSearch request: {method} {endpoint} -> {status_code} ({duration_ms}ms)',
            extra=log_extra,
        )
    else:
        logger.error(
            f'OpenSearch request failed: {method} {endpoint} -> {status_code} ({duration_ms}ms)',
            extra=log_extra,
        )


class BufferedAsyncHttpConnection(AsyncHttpConnection):
    """Async HTTP connection that buffers responses with size limiting.

    This connection class prevents large responses from being loaded into memory
    by streaming the response and checking size limits during processing. If the
    response exceeds max_response_size, it stops reading and raises an exception
    before the complete response is downloaded.
    """

    def __init__(self, *args, max_response_size=DEFAULT_MAX_RESPONSE_SIZE, **kwargs):
        """Initialize buffered connection with response size limit.

        Args:
            *args: Arguments passed to parent AsyncHttpConnection.
            max_response_size: Maximum allowed response size in bytes (default: 10 MiB).
                Pass ``None`` to disable the limit (delegates to the parent connection).
            **kwargs: Keyword arguments passed to parent AsyncHttpConnection.
        """
        super().__init__(*args, **kwargs)
        self.max_response_size = max_response_size
        if max_response_size is not None:
            logger.debug(
                f'Initialized BufferedAsyncHttpConnection with max_response_size={max_response_size} bytes'
            )
        else:
            logger.debug('Initialized BufferedAsyncHttpConnection with no response size limit')

    async def perform_request(
        self, method, url, params=None, body=None, timeout=None, ignore=(), headers=None
    ):
        """Perform HTTP request with response size limiting.

        This implementation leverages the parent class for authentication and session management
        but implements streaming response size checking to prevent memory exhaustion from large responses.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            params: Query parameters
            body: Request body
            timeout: Request timeout
            ignore: HTTP status codes to ignore
            headers: Additional headers

        Returns:
            Tuple of (status, headers, response_data)

        Raises:
            ResponseSizeExceededError: If response exceeds max_response_size during streaming
        """
        # When no limit is configured, there is nothing this subclass adds over the
        # parent — delegate entirely so we inherit the parent's auth, TLS, gzip,
        # warning handling, and aiohttp->opensearch-py exception translation verbatim
        # (no risk of drift, and no second buffering pass).
        if self.max_response_size is None:
            return await super().perform_request(
                method,
                url,
                params=params,
                body=body,
                timeout=timeout,
                ignore=ignore,
                headers=headers,
            )

        logger.debug(
            f'Making size-limited request: {method} {url} (max_size={self.max_response_size})'
        )
        original_url = url

        # Import required modules
        import aiohttp
        import asyncio
        import yarl

        # For reproducing the parent's exception translation (see the except blocks
        # below): without the old fallback path, transport errors must still surface
        # as the opensearch-py types callers expect — never a raw aiohttp error, and
        # never by re-issuing the request.
        from opensearchpy.compat import reraise_exceptions
        from opensearchpy.exceptions import (
            ConnectionError,
            ConnectionTimeout,
            SSLError,
            TransportError,
        )
        from urllib.parse import urlencode

        # Hoisted above the try: so the except handler can always reference them, even
        # if the failure occurs during session/auth setup (e.g. an SSL/session error —
        # exactly the transport failure the handler translates). Assigning them inside
        # the try would leave them unbound and raise UnboundLocalError, masking the
        # real exception. ``start`` uses ``time.monotonic`` (not ``self.loop.time``)
        # because ``self.loop`` is only populated once the session is created, which
        # happens inside the try — and is only used here for duration logging.
        orig_body = body
        url_path = self.url_prefix + url
        start = time.monotonic()

        try:
            # Ensure session is created (from parent class)
            if self.session is None:
                await self._create_aiohttp_session()
            assert self.session is not None

            # Build URL and prepare request (following parent class logic)
            if params:
                query_string = urlencode(params)
            else:
                query_string = ''

            url = self.url_prefix + url
            if query_string:
                url = f'{url}?{query_string}'
            url = self.host + url

            timeout_obj = aiohttp.ClientTimeout(
                total=timeout if timeout is not None else self.timeout
            )

            # Prepare headers (following parent class logic)
            req_headers = self.headers.copy()
            if headers:
                req_headers.update(headers)

            if self.http_compress and body:
                body = self._gzip_compress(body)
                req_headers['content-encoding'] = 'gzip'

            # Handle authentication (following parent class logic)
            auth = self._http_auth if isinstance(self._http_auth, aiohttp.BasicAuth) else None
            if callable(self._http_auth):
                req_headers = {
                    **req_headers,
                    **self._http_auth(method=method, url=url, body=body, headers=req_headers),
                }

            # Make request with streaming response handling
            async with self.session.request(
                method,
                yarl.URL(url, encoded=True),
                data=body,
                auth=auth,
                headers=req_headers,
                timeout=timeout_obj,
                fingerprint=self.ssl_assert_fingerprint,
            ) as response:
                # Stream the response with optional size checking
                chunks = []
                total_size = 0

                async for chunk in response.content.iter_chunked(8192):
                    # Only check size limit if max_response_size is set
                    if (
                        self.max_response_size is not None
                        and total_size + len(chunk) > self.max_response_size
                    ):
                        duration = time.monotonic() - start
                        self.log_request_fail(
                            method,
                            str(url),
                            url_path,
                            orig_body,
                            duration,
                            exception=f'Response size exceeded {self.max_response_size} bytes',
                        )
                        logger.error(
                            f'Response size exceeded limit during streaming: '
                            f'{total_size + len(chunk)} > {self.max_response_size} bytes'
                        )
                        raise ResponseSizeExceededError(
                            f'Response size exceeded limit of {self.max_response_size} bytes. '
                            f'Stopped reading at {total_size} bytes to prevent memory exhaustion. '
                            f'Consider increasing max_response_size or refining your query to return less data.'
                        )

                    chunks.append(chunk)
                    total_size += len(chunk)

                # Combine all chunks and decode. Use 'surrogatepass' to match the
                # parent (opensearch-py) decode exactly — a plain 'utf-8' decode with
                # a str(bytes) fallback would corrupt valid responses containing
                # surrogate code points.
                response_data = b''.join(chunks)
                raw_data = response_data.decode('utf-8', 'surrogatepass')

                duration = time.monotonic() - start

            # Handle warnings (following parent class logic)
            warning_headers = response.headers.getall('warning', ())
            self._raise_warnings(warning_headers)

            # Handle errors (following parent class logic)
            duration_ms = round(duration * 1000, 2)
            if not (200 <= response.status < 300) and response.status not in ignore:
                self.log_request_fail(
                    method,
                    str(url),
                    url_path,
                    orig_body,
                    duration,
                    status_code=response.status,
                    response=raw_data,
                )
                _log_request_event(
                    method,
                    original_url,
                    response.status,
                    duration_ms,
                    'error',
                    response_size=total_size,
                )
                self._raise_error(response.status, raw_data)

            # Log success
            self.log_request_success(
                method, str(url), url_path, orig_body, response.status, raw_data, duration
            )
            _log_request_event(
                method,
                original_url,
                response.status,
                duration_ms,
                'success',
                response_size=total_size,
            )

            return response.status, response.headers, raw_data

        except reraise_exceptions:
            # RecursionError / CancelledError — propagate as-is (matches parent).
            raise
        except (ResponseSizeExceededError, TransportError):
            # Our own size guard, and HTTP-status errors raised by _raise_error
            # (NotFoundError/RequestError/etc.) must propagate unchanged. We do NOT
            # retry or re-issue the request (the old fallback double-issued every
            # 4xx/5xx — dangerous for non-idempotent writes).
            raise
        except Exception as e:
            # Translate genuine transport failures exactly as the parent does, so
            # callers see the opensearch-py exception types they expect.
            duration = time.monotonic() - start
            self.log_request_fail(method, str(url), url_path, orig_body, duration, exception=e)
            _log_request_event(
                method, original_url, None, round(duration * 1000, 2), 'error', error=str(e)
            )
            if isinstance(e, aiohttp.ServerFingerprintMismatch):
                raise SSLError('N/A', str(e), e)
            if isinstance(e, (asyncio.TimeoutError, aiohttp.ServerTimeoutError)):
                raise ConnectionTimeout('TIMEOUT', str(e), e)
            raise ConnectionError('N/A', str(e), e)
