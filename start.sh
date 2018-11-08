gunicorn -w 4 wsgi:stegoproxy -b 127.0.0.1:$PORT --log-file logs/gunicorn.log --pid gunicorn.pid --reload -D
