# Deployment notes

## Client IP and rate limits

The backend keys rate limits and the wrong-password lockout on the client IP. Behind the Google load
balancer set `TRUSTED_PROXY_HOPS=1`: the LB appends `<client>, <lb>` to `X-Forwarded-For`, so the entry
second from the right is the client. That position is trusted by contract (it must also parse as an IP,
otherwise the socket peer is used); anything a caller puts further left is ignored.

In-cluster callers (the traffic generator, `kubectl port-forward`) do not pass through the LB, so there
is no trusted hop for them. They can forge `X-Forwarded-For` to pick their own limiter key, which is
acceptable here because the generator makes at most 1-2 requests per 5 minutes and in-cluster access is
already trusted. If untrusted in-cluster callers ever exist, set `TRUSTED_PROXY_HOPS=0` for that
deployment so the socket peer is always used.
