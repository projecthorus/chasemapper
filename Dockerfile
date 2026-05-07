# -------------------
# The build container
# -------------------
FROM python:3.11-bookworm AS build

# Upgrade base packages.
RUN apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y \
  cmake \
  libgeos-dev \
  libatlas-base-dev && \
  rm -rf /var/lib/apt/lists/*

# Copy in existing wheels.
COPY wheel[s]/ /root/.cache/pip/wheels/

# No wheels might exist.
RUN mkdir -p /root/.cache/pip/wheels/

# Copy in requirements.txt.
COPY requirements.txt /root/chasemapper/requirements.txt

# Install Python packages.
# Added --no-cache-dir to avoid pip caching wheels in the build stage.
RUN pip3 install --user --break-system-packages --no-warn-script-location \
  --no-cache-dir \
  --ignore-installed -r /root/chasemapper/requirements.txt

# NOTE: removed `COPY . /root/chasemapper` — the build stage only needs
# requirements.txt and the cusf wrapper below. Skipping this also means
# editing python files won't bust the pip-install cache layer.

# Download and install cusf_predictor_wrapper, and build predictor binary.
ADD https://github.com/darksidelemm/cusf_predictor_wrapper/archive/master.zip \
  /root/cusf_predictor_wrapper-master.zip
RUN unzip /root/cusf_predictor_wrapper-master.zip -d /root && \
  rm /root/cusf_predictor_wrapper-master.zip && \
  mkdir -p /root/cusf_predictor_wrapper-master/src/build && \
  cd /root/cusf_predictor_wrapper-master/src/build && \
  cmake .. && \
  make

# Strip bytecode, test suites, and debug symbols before copying to final stage.
# tests/ dirs in numpy/scipy/etc. can be 100+ MB combined.
# Stripping .so debug symbols typically saves another 50-200 MB.
RUN find /root/.local -name "*.pyc" -delete && \
  find /root/.local -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true && \
  find /root/.local -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true && \
  find /root/.local -type d -name "test" -exec rm -rf {} + 2>/dev/null || true && \
  find /root/.local -name "*.so" -exec strip --strip-unneeded {} + 2>/dev/null || true

# -------------------------
# The application container
# -------------------------
FROM python:3.11-slim-bookworm
EXPOSE 5001/tcp

# Upgrade base packages and install application dependencies.
# Removed libatlas3-base — numpy wheels from PyPI bundle their own OpenBLAS.
# Removed libgfortran5 — only needed if something dynamically links to it.
# If chasemapper fails to start with an "import" or "shared library" error,
# add these back one at a time.
RUN apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y \
  libeccodes0 \
  libgeos-c1v5 \
  libglib2.0-0 \
  tini && \
  rm -rf /var/lib/apt/lists/*

# Copy any additional Python packages from the build container.
COPY --from=build /root/.local /root/.local

# Copy predictor binary from the build container.
COPY --from=build /root/cusf_predictor_wrapper-master/src/build/pred \
  /opt/chasemapper/

# Copy in chasemapper.
# Make sure .dockerignore excludes .git, docs, screenshots, etc.
COPY . /opt/chasemapper

# Set the working directory.
WORKDIR /opt/chasemapper

# Persist the airspace/TFR cache across container restarts.
RUN mkdir -p /opt/chasemapper/cache/airspace
VOLUME ["/opt/chasemapper/cache"]

# Ensure scripts from Python packages are in PATH.
ENV PATH=/root/.local/bin:$PATH

# Use tini as init.
ENTRYPOINT ["/usr/bin/tini", "--"]

# Run horusmapper.py.
CMD ["python3", "/opt/chasemapper/horusmapper.py"]