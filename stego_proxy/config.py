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
        "stego_proxy": {
            "level": "ERROR",
            "formatter": "standard",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join("../", "stego_proxy.log"),
            "mode": "a",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
        },
    },
    "loggers": {
        "stego_proxy": {
            "handlers": ["console", "stego_proxy"],
            "level": "DEBUG",
            "propagate": False,
        }
    },
}
