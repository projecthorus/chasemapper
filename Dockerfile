# -------------------
# The build container
# -------------------
FROM python:3.7-buster AS build

# Upgrade base packages.
RUN apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y \
  cmake \
  libgdal-dev && \
  rm -rf /var/lib/apt/lists/*

# Copy in requirements.txt.
COPY requirements.txt \
  /root/chasemapper/requirements.txt

# Install numpy Python package first so that it is available for gdal.
RUN pip3 --no-cache-dir install --user --no-warn-script-location \
  --extra-index-url https://www.piwheels.org/simple \
  numpy

# Install remaining Python packages.
RUN pip3 --no-cache-dir install --user --no-warn-script-location \
  --extra-index-url https://www.piwheels.org/simple \
  -r /root/chasemapper/requirements.txt

# Copy in chasemapper.
COPY . /root/chasemapper

# Download and install cusf_predictor_wrapper, and build predictor binary.
ADD https://github.com/darksidelemm/cusf_predictor_wrapper/archive/master.zip /root/cusf_predictor_wrapper-master.zip
RUN unzip /root/cusf_predictor_wrapper-master.zip -d /root && \
  rm /root/cusf_predictor_wrapper-master.zip && \
  cd /root/cusf_predictor_wrapper-master && \
  python3 setup.py install --user && \
  cd src && \
  mkdir build && \
  cd build && \
  cmake ../ && \
  make

# -------------------------
# The application container
# -------------------------
FROM python:3.7-slim-buster
EXPOSE 5001/tcp

# Upgrade base packages and install application dependencies.
RUN apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y \
  libgdal20 \
  libglib2.0 \
  tini && \
  rm -rf /var/lib/apt/lists/*

# Copy any additional Python packages from the build container.
COPY --from=build /root/.local /root/.local

# Copy predictor binary and get_wind_data.py from the build container.
COPY --from=build /root/cusf_predictor_wrapper-master/src/build/pred /opt/chasemapper/
COPY --from=build /root/cusf_predictor_wrapper-master/apps/get_wind_data.py /opt/chasemapper/

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
