# Isolated Linux root fixture for the finite transport owner. No host sudo,
# runtime credentials, daemon sockets, privileged capabilities or network.
FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    python3.12 python3-pytest git \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONPATH=/repo PYTHONDONTWRITEBYTECODE=1 MM_APPLICATION_TRANSPORT_TEST_ROOT=/fixture
WORKDIR /repo
USER 0:0
CMD ["/usr/bin/python3.12", "-B", "tests/application_tunnel_ci/require_proof.py"]
