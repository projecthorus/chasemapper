# -------------------
# The build container
# -------------------
FROM python:3.9-bullseye AS build

# Upgrade base packages.
RUN apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y \
  cmake \
  libgeos-dev \
  libatlas3-base-dev && \
  rm -rf /var/lib/apt/lists/*

# Copy in requirements.txt.
COPY requirements.txt /root/chasemapper/requirements.txt

# Install Python packages.
RUN pip3 --no-cache-dir install --user --no-warn-script-location \
  --extra-index-url https://www.piwheels.org/simple \
  -r /root/chasemapper/requirements.txt

# Copy in chasemapper.
COPY . /root/chasemapper

# Download and install cusf_predictor_wrapper, and build predictor binary.
ADD https://github.com/darksidelemm/cusf_predictor_wrapper/archive/master.zip \
  /root/cusf_predictor_wrapper-master.zip
RUN unzip /root/cusf_predictor_wrapper-master.zip -d /root && \
  rm /root/cusf_predictor_wrapper-master.zip && \
  mkdir -p /root/cusf_predictor_wrapper-master/src/build && \
  cd /root/cusf_predictor_wrapper-master/src/build && \
  cmake .. && \
  make

# -------------------------
# The application container
# -------------------------
FROM python:3.9-slim-bullseye
EXPOSE 5001/tcp

# Upgrade base packages and install application dependencies.
RUN case $(uname -m) in \
    "armv6l") extra_packages="libatlas3-base libgfortran5" ;; \
    "armv7l") extra_packages="libatlas3-base libgfortran5" ;; \
  esac && \
  apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y \
  libatlas3-base \
  libeccodes0 \
  libgeos-c1v5 \
  libglib2.0-0 \
  ${extra_packages} \
  tini && \
  rm -rf /var/lib/apt/lists/*

# Copy any additional Python packages from the build container.
COPY --from=build /root/.local /root/.local

# Copy predictor binary from the build container.
COPY --from=build /root/cusf_predictor_wrapper-master/src/build/pred \
  /opt/chasemapper/

# Copy in chasemapper.
COPY . /opt/chasemapper

# Set the working directory.
WORKDIR /opt/chasemapper

# Ensure scripts from Python packages are in PATH.
ENV PATH=/root/.local/bin:$PATH

# Use tini as init.
ENTRYPOINT ["/usr/bin/tini", "--"]

# Run horusmapper.py.
CMD ["python3", "/opt/chasemapper/horusmapper.py"]
