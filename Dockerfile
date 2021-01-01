# -------------------
# The build container
# -------------------
FROM debian:buster-slim AS build

# Update system packages and install build dependencies.
RUN apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y \
  build-essential \
  cmake \
  libglib2.0-dev \
  python \
  python-dateutil \
  python-fastkml \
  python-flask \
  python-gdal \
  python-numpy \
  python-pip \
  python-requests \
  python-serial \
  python-setuptools \
  python-shapely \
  unzip && \
  rm -rf /var/lib/apt/lists/*

# Install additional Python packages that aren't available through apt-get.
RUN pip --no-cache-dir install \
  flask-socketio==4.3.2 \
  pytz

# Download and install cusf_predictor_wrapper, and build predictor binary.
ADD https://github.com/darksidelemm/cusf_predictor_wrapper/archive/master.zip /root/cusf_predictor_wrapper-master.zip
RUN unzip /root/cusf_predictor_wrapper-master.zip -d /root && \
  rm /root/cusf_predictor_wrapper-master.zip && \
  cd /root/cusf_predictor_wrapper-master && \
  python setup.py install && \
  cd src && \
  mkdir build && \
  cd build && \
  cmake ../ && \
  make

# -------------------------
# The application container
# -------------------------
FROM debian:buster-slim
EXPOSE 5001/tcp

# Update system packages and install build dependencies.
RUN apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y \
  libglib2.0 \
  python \
  python-dateutil \
  python-fastkml \
  python-flask \
  python-gdal \
  python-numpy \
  python-requests \
  python-serial \
  python-shapely \
  unzip && \
  rm -rf /var/lib/apt/lists/*

# Copy any additional Python packages from the build container.
COPY --from=build /usr/local/lib/python2.7/dist-packages /usr/local/lib/python2.7/dist-packages

# Copy predictor binary and get_wind_data.py from the build container.
COPY --from=build /root/cusf_predictor_wrapper-master/src/build/pred /opt/chasemapper/
COPY --from=build /root/cusf_predictor_wrapper-master/apps/get_wind_data.py /opt/chasemapper/

# Copy in chasemapper.
COPY . /opt/chasemapper

# Run horusmapper.py.
WORKDIR /opt/chasemapper
CMD ["python", "/opt/chasemapper/horusmapper.py"]
