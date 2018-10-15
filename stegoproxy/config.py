import os

LOG_DEFAULT_CONF = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "standard": {
            "format": "%(asctime)-10s %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "colored": {
            "()": "colorlog.ColoredFormatter",
            "format": "%(log_color)s%(levelname)-8s%(reset)s %(blue)s%(message)s",  # noqa
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "formatter": "colored",
            "class": "logging.StreamHandler",
        },
        "stegoproxy": {
            "level": "ERROR",
            "formatter": "standard",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join("../", "stegoproxy.log"),
            "mode": "a",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
        },
    },
    "loggers": {
        "stegoproxy": {
            "handlers": ["console", "stegoproxy"],
            "level": "DEBUG",
            "propagate": False,
        }
    },
}


class Config(object):
    LOGGING_CONFIG = LOG_DEFAULT_CONF
    ALGORITHM = None
    REMOTE_ADDR = None
    HTTP_COMMAND = "POST"
    HTTP_PATH = "/"
    HTTP_VERSION = "HTTP/1.1"


cfg = Config()
