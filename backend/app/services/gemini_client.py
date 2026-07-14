import logging
import json
import asyncio
import httpx
from typing import Dict, Any, Optional, Tuple, List
from app.config import settings

logger = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL
        self.api_version = "v1beta"
        self.base_url = "https://generativelanguage.googleapis.com"

    def get_url(self) -> str:
        """Constructs the full Gemini API URL for generateContent."""
        model_name = self.model.strip()
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"
        return f"{self.base_url}/{self.api_version}/{model_name}:generateContent?key={self.api_key}"

    def get_masked_url(self) -> str:
        """Constructs a masked Gemini API URL for logging purposes."""
        model_name = self.model.strip()
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"
        return f"{self.base_url}/{self.api_version}/{model_name}:generateContent?key=REDACTED"

    def get_headers(self) -> Dict[str, str]:
        """Returns standard headers for Gemini API requests."""
        return {
            "Content-Type": "application/json"
        }

    async def post_request(
        self,
        payload: Dict[str, Any],
        client: Optional[httpx.AsyncClient] = None,
        timeout: float = 30.0
    ) -> httpx.Response:
        """
        Sends a POST request to the Gemini API and returns the response.
        Raises httpx.HTTPStatusError for non-200 responses to be caught by the retry handler.
        """
        url = self.get_url()
        masked_url = self.get_masked_url()
        headers = self.get_headers()
        timeout_cfg = httpx.Timeout(connect=3.0, read=timeout, write=3.0, pool=5.0)

        # Confirm API Key is loaded
        if not self.api_key:
            logger.error(
                f"Gemini API request failed. API key missing. "
                f"Model: {self.model}, Endpoint: {masked_url}, Exception Type: ValueError, "
                f"Exception Message: GEMINI_API_KEY is missing."
            )
            raise ValueError("GEMINI_API_KEY is missing.")

        logger.info(f"Initiating Gemini request. Model: {self.model}, Endpoint: {masked_url}")
        
        try:
            if client is not None:
                response = await client.post(url, json=payload, headers=headers, timeout=timeout_cfg)
            else:
                async with httpx.AsyncClient(timeout=timeout_cfg) as local_client:
                    response = await local_client.post(url, json=payload, headers=headers)
        except Exception as e:
            logger.error(
                f"Gemini connection failed. "
                f"Model: {self.model}, Endpoint: {masked_url}, "
                f"Exception Type: {type(e).__name__}, Exception Message: {str(e)}"
            )
            raise

        if response.status_code != 200:
            self._log_error_status(response.status_code, response.text)
            logger.error(
                f"Gemini request failed. HTTP Status: {response.status_code}, "
                f"Model: {self.model}, Endpoint: {masked_url}, "
                f"Error Body: {response.text}"
            )
            response.raise_for_status()

        logger.info(f"Gemini request succeeded. Model: {self.model}, Endpoint: {masked_url}")
        return response

    async def post_request_with_retry(
        self,
        payload: Dict[str, Any],
        client: Optional[httpx.AsyncClient] = None,
        timeout: float = 30.0
    ) -> httpx.Response:
        """
        Sends a POST request to the Gemini API with intelligent retry rules and exponential backoff.
        Retries only on transient failures (429, 500, 502, 503, timeouts, network issues).
        """
        max_retries = 3
        delay = 1.0
        masked_url = self.get_masked_url()
        
        for attempt in range(1, max_retries + 1):
            try:
                response = await self.post_request(payload, client, timeout)
                return response
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code in [429, 500, 502, 503]:
                    if attempt == max_retries:
                        logger.error(
                            f"Gemini API request failed after {max_retries} attempts with status {status_code}. "
                            f"Model: {self.model}, Endpoint: {masked_url}, Exception Type: HTTPStatusError, "
                            f"Exception Message: {str(e)}"
                        )
                        raise
                    logger.warning(
                        f"Gemini API returned transient status {status_code}. "
                        f"Retrying in {delay:.1f}s (attempt {attempt}/{max_retries})..."
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    # Do not retry on permanent errors (400, 401, 403, 404)
                    logger.error(
                        f"Gemini API returned non-retryable status {status_code}. Aborting retries. "
                        f"Model: {self.model}, Endpoint: {masked_url}, Exception Type: HTTPStatusError, "
                        f"Exception Message: {str(e)}"
                    )
                    raise
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt == max_retries:
                    logger.error(
                        f"Gemini API request failed after {max_retries} attempts due to connection/timeout error: {e}. "
                        f"Model: {self.model}, Endpoint: {masked_url}, Exception Type: {type(e).__name__}, "
                        f"Exception Message: {str(e)}"
                    )
                    raise
                logger.warning(
                    f"Gemini API encountered connection/timeout error: {e}. "
                    f"Retrying in {delay:.1f}s (attempt {attempt}/{max_retries})...."
                )
                await asyncio.sleep(delay)
                delay *= 2

        raise RuntimeError("Unexpected end of retry loop in GeminiClient")

    def _log_error_status(self, status_code: int, response_text: str):
        """Logs precise explanations for Gemini API error status codes."""
        try:
            err_data = json.loads(response_text)
            err_msg = err_data.get("error", {}).get("message", "No message details provided")
        except Exception:
            err_msg = response_text[:500]

        if status_code == 400:
            logger.error(f"Gemini API Bad Request (400): {err_msg}. Check payload structure or parameters.")
        elif status_code == 401:
            logger.error(f"Gemini API Unauthorized (401): {err_msg}. Please check if GEMINI_API_KEY is correct.")
        elif status_code == 403:
            logger.error(f"Gemini API Forbidden (403): {err_msg}. Access denied or restriction active.")
        elif status_code == 404:
            logger.error(f"Gemini API Not Found (404): {err_msg}. Model '{self.model}' might be retired, invalid, or unavailable.")
        elif status_code == 429:
            logger.error(f"Gemini API Rate Limit / Quota Exceeded (429): {err_msg}.")
        elif 500 <= status_code < 600:
            logger.error(f"Gemini API Internal Server Error ({status_code}): {err_msg}.")
        else:
            logger.error(f"Gemini API returned status {status_code}: {err_msg}.")


async def validate_gemini_config() -> bool:
    """
    Validates the configured Gemini model during application startup.
    Performs a lightweight GET request to query the model metadata.
    Logs warnings or errors clearly to prevent silent run-time failures.
    """
    api_key = settings.GEMINI_API_KEY
    model = settings.GEMINI_MODEL
    
    if not api_key:
        logger.warning("GEMINI_API_KEY is not configured in settings. Gemini features will use local fallback paths.")
        return False

    model_clean = model.strip()
    if not model_clean.startswith("models/"):
        model_clean = f"models/{model_clean}"

    url = f"https://generativelanguage.googleapis.com/v1beta/{model_clean}?key={api_key}"
    
    try:
        timeout = httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                supported_methods = data.get("supportedGenerationMethods", [])
                if "generateContent" in supported_methods:
                    logger.info(f"Gemini model '{model}' successfully validated at startup and supports generateContent.")
                    return True
                else:
                    logger.error(f"Gemini model '{model}' is valid but does NOT support generateContent (supported: {supported_methods}).")
                    return False
            elif response.status_code == 404:
                logger.error(f"Gemini model validation failed: Model '{model}' was not found (HTTP 404). It may be retired or unavailable.")
                return False
            elif response.status_code == 401:
                logger.error("Gemini API validation failed: The API key is invalid or unauthorized (HTTP 401).")
                return False
            elif response.status_code == 403:
                logger.error("Gemini API validation failed: Access forbidden (HTTP 403).")
                return False
            elif response.status_code == 429:
                logger.warning(f"Gemini model validation was rate-limited (HTTP 429). Assuming model '{model}' is valid.")
                return True
            else:
                logger.warning(f"Gemini model validation returned status {response.status_code}: {response.text[:200]}")
                return False
    except Exception as e:
        logger.warning(f"Failed to validate Gemini configuration on startup due to network/unexpected error: {e}")
        return False
