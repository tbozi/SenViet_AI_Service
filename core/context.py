import contextvars
current_session_id = contextvars.ContextVar('current_session_id', default=None)
