httperf \
    --server 127.0.0.1 \
    --port 8888 \
    --uri=http://stego.local:5000/randomfile \
    --no-host-hdr \
    --add-header "Host: stego.local:5000" \
    --hog --num-conn 100 --ra 10 --timeout 5


