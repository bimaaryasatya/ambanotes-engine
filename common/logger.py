import logging
import datetime

def get_logger(name):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(name)
    return logger

def log_event(
    service_name,
    message,
    user_id=None,
    org_id=None,
    action=None,
    metadata=None,
    audience="developer",
    visibility="internal",
    severity="info",
):
    """
    Log an event to the database and console.
    
    Args:
        service_name (str): Name of the service (e.g., 'auth_service')
        message (str): Human-readable log message
        user_id (str, optional): ID of the user who performed the action
        org_id (str, optional): Organization ID related to the action
        action (str, optional): Action type (e.g., 'LOGIN_SUCCESS', 'DOC_DELETE')
        metadata (dict, optional): Additional structured data
        audience (str, optional): Target audience: user, owner, developer
        visibility (str, optional): Surface: app, dashboard, internal
        severity (str, optional): Severity level: info, warning, error, debug
    """
    logger = get_logger(service_name)
    log_method = getattr(logger, severity.lower(), logger.info)
    log_method(message)
    
    # Import inside function to avoid circular dependencies
    from common.db import logs_col
    
    log_data = {
        "service": service_name,
        "message": message,
        "user_id": user_id,
        "org_id": org_id,
        "action": action,
        "metadata": metadata or {},
        "audience": audience,
        "visibility": visibility,
        "severity": severity,
        "timestamp": datetime.datetime.utcnow()
    }
    
    try:
        logs_col.insert_one(log_data)
    except Exception as e:
        logger.error(f"Failed to save log to database: {str(e)}")
