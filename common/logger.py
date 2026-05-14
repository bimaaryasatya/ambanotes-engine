import logging

def get_logger(name):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(name)
    return logger

def log_event(service_name, message):
    logger = get_logger(service_name)
    logger.info(message)
