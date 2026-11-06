FROM alpine:3.24
RUN apk add --no-cache keepalived curl
ENTRYPOINT ["keepalived", "--dont-fork", "--log-console", "--use-file=/etc/keepalived/keepalived.conf"]
