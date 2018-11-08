import os

_base_dir = os.path.dirname(os.path.dirname(__file__))


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
            "format": "%(log_color)s%(levelname)-8s%(reset)s %(cyan)s%(message)s",  # noqa
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
            "filename": os.path.join(_base_dir, "logs", "stegoproxy.log"),
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
    BASE_DIR = _base_dir
    LOGGING_CONFIG = LOG_DEFAULT_CONF
    ALGORITHM = None    # If None: defaults to "base64"
    REMOTE_ADDR = None  # If None: defaults to "localhost:9999"
    STEGO_HTTP_COMMAND = "POST"
    STEGO_HTTP_PATH = "/"
    STEGO_HTTP_VERSION = "HTTP/1.1"
    # Used to hide the stegoserver behind a real website
    REVERSE_HOSTNAME = "peterjustin.me"

    MAX_CONTENT_LENGTH = 500000  # in bytes
    # Available algorithms:
    #  - null: Doesn't hide the message (just encodes and it decodes it in b64)
    #  - stegano_lsb
    STEGO_ALGORITHM = "stegano_exif"
    # Path to the folder that contains the cover objects
    COVER_PATH = os.path.join(_base_dir, "coverobjects")
    COVER_OBJECTS = ["handsome.jpeg", "img1.png", "handsome.png"]


cfg = Config()
