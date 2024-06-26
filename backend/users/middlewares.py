import logging

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class LogMiddleware(MiddlewareMixin):
    def process_request(self, request):
        logger.debug(f"Request received: {request.path}")
        return None
