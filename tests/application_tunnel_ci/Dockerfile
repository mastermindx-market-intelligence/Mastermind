# Isolated Linux root fixture for the finite transport owner. No host sudo,
# runtime credentials, daemon sockets, privileged capabilities or network.
FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
ENV DEBIAN_FRONTEND=noninteractive
# Refresh the complete package transaction if a publishing mirror or HTTP cache
# exposes an index before its packages. Every failed attempt remains visible.
RUN set -eu; \
    for application_apt_attempt in 1 2 3; do \
        rm -rf /var/lib/apt/lists/*; \
        if apt-get -o Acquire::http::No-Cache=true update --error-on=any \
            && apt-get -o Acquire::http::No-Cache=true install -y --no-install-recommends \
                python3.12 python3-pytest git; then \
            rm -rf /var/lib/apt/lists/*; \
            break; \
        fi; \
        if [ "$application_apt_attempt" -eq 3 ]; then \
            echo "Isolated transport fixture dependency acquisition failed after 3 attempts" >&2; \
            exit 1; \
        fi; \
        sleep 5; \
    done
ENV PYTHONPATH=/repo PYTHONDONTWRITEBYTECODE=1 MM_APPLICATION_TRANSPORT_TEST_ROOT=/fixture
WORKDIR /repo
USER 0:0
CMD ["/usr/bin/python3.12", "-B", "tests/application_tunnel_ci/require_proof.py"]

