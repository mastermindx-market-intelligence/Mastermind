# Test-only non-root Linux principal with a fresh no-default-ACL HOME.
# Production initializer permissions and ACL predicate are untouched.
# Digest pins the Ubuntu 24.04 root filesystem used for this environment.
FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    python3.12 python3-pytest python3-venv passwd \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 1555 --create-home --home-dir /home/mmx-h1-fixture \
    --shell /bin/sh mmx-h1-fixture
USER mmx-h1-fixture
ENV HOME=/home/mmx-h1-fixture PYTHONPATH=/repo
WORKDIR /repo
# Ubuntu 24.04 distro packaging contains two administrative symlinks in the
# fixed Root Python 3.12 startup directory. The normal-profile initializer
# correctly refuses them. This disposable image preserves their exact target
# bytes as regular Root-owned files; it never changes a host path or ACL.
USER root
RUN set -eu; for node in \
  /usr/lib/python3.12/sitecustomize.py \
  /usr/lib/python3.12/_sysconfigdata__linux_x86_64-linux-gnu.py; do \
    if [ -L "$node" ]; then \
      src="$(readlink -f -- "$node")"; \
      test -f "$src"; \
      original="$(sha256sum "$src" | cut -d' ' -f1)"; \
      cp --remove-destination -- "$src" "$node"; \
      test ! -L "$node"; \
      test "$(sha256sum "$node" | cut -d' ' -f1)" = "$original"; \
    else test -f "$node"; fi; \
  done
USER mmx-h1-fixture
