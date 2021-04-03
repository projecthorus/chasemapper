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
  python3 \
  python3-dateutil \
  python3-fastkml \
  python3-flask \
  python3-gdal \
  python3-numpy \
  python3-pip \
  python3-requests \
  python3-serial \
  python3-setuptools \
  python3-shapely \
  unzip && \
  rm -rf /var/lib/apt/lists/*

# Install additional Python packages that aren't available through apt-get.
RUN pip3 --no-cache-dir install \
  flask-socketio \
  pytz

# Download and install cusf_predictor_wrapper, and build predictor binary.
ADD https://github.com/darksidelemm/cusf_predictor_wrapper/archive/master.zip /root/cusf_predictor_wrapper-master.zip
RUN unzip /root/cusf_predictor_wrapper-master.zip -d /root && \
  rm /root/cusf_predictor_wrapper-master.zip && \
  cd /root/cusf_predictor_wrapper-master && \
  python3 setup.py install && \
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
  python3 \
  python3-dateutil \
  python3-fastkml \
  python3-flask \
  python3-gdal \
  python3-numpy \
  python3-requests \
  python3-serial \
  python3-shapely \
  unzip && \
  rm -rf /var/lib/apt/lists/*

# Copy any additional Python packages from the build container.
COPY --from=build /usr/local/lib/python3.7/dist-packages /usr/local/lib/python3.7/dist-packages

# Copy predictor binary and get_wind_data.py from the build container.
COPY --from=build /root/cusf_predictor_wrapper-master/src/build/pred /opt/chasemapper/
COPY --from=build /root/cusf_predictor_wrapper-master/apps/get_wind_data.py /opt/chasemapper/

# Copy in chasemapper.
COPY . /opt/chasemapper

# Run horusmapper.py.
WORKDIR /opt/chasemapper
CMD ["python3", "/opt/chasemapper/horusmapper.py"]
