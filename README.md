# Steganography Proxy

_A HTTP Proxy that uses steganographic algorithms for establishing covert
communication channels._

# Usage

It is advised to execute these commands inside a
[virtualenv](https://virtualenv.pypa.io/en/stable/userguide/) in order to not
pollute your system.

Install from local disk (make sure to be inside the directory where the `setup.py` file
is located):
```bash
pip install -r requirements-dev.txt
```

Start the stegoproxy server (listens on port `9999` by default):
```bash
stegoproxy server
```

Start the stegoproxy client (listens on port `8888` by default):
```bash
stegoproxy client
```

stegoproxy also ships a very barebones flask app (port `5000`) to test it's
functionality:
```bash
stegoproxy demoapp
```

Type `stegoproxy --help` to see a list of available commands and `stegoproxy
[COMMAND]  --help` to get help for a specific command.
