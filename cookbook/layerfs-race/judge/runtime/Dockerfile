# Runtime image for the LayerFS Sandboxes in this demo.
# Vendored from github.com/Ephemeral-AI-Lab/layerfs (MIT),
# dsh/tools/history/runtime/Dockerfile — it is not in tag v0.1.7, so a copy
# is kept here. Only the base image matters for the race: Node 24 bookworm
# pinned by digest, with git/patch/python3 from the Debian buildpack base.
FROM node:24.21.0-bookworm@sha256:3d27e5c11e5786e309ec3e03f93ae536eb36e6e5eb3714d5eb3300a36157add0

ENV COREPACK_HOME=/opt/corepack \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    COREPACK_ENABLE_AUTO_PIN=0

RUN corepack enable \
 && corepack install --global pnpm@11.28.5 \
 && corepack prepare pnpm@11.7.0 pnpm@11.28.5 yarn@4.14.1 \
 && chmod -R a+rX /opt/corepack

ENV COREPACK_ENABLE_NETWORK=0 \
    CI=1

LABEL org.opencontainers.image.title="layerfs-race-runtime" \
      org.opencontainers.image.description="Node 24 with pnpm/yarn prepared offline (vendored from layerfs dsh/tools/history/runtime)"

CMD ["bash"]
