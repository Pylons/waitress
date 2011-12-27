import asyncore

import logging
logger = logging.getLogger('waitress')

class logging_dispatcher(asyncore.dispatcher):
    def log_info(self, message, type='info'):
        severity = {
            'info': logging.INFO,
            'warning': logging.WARN,
            'error': logging.ERROR,
            }
        logger.log(severity.get(type, logging.INFO), message)

