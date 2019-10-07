#!/bin/sh

echo "Installing initial dependencies..."
apt-get install libglib2.0-dev \
  libgirepository1.0-dev \
  libcairo2-dev \
  python3-venv \
  autoconf \
  automake \
  libtool \
  pkg-config \
  libgstreamer1.0-dev \
  libgstreamer-plugins-base1.0-dev \
  libraspberrypi-dev \
  python3-dev \
  libffi-dev \
  libssl-dev -y

echo "Upgrading to python3.6..."
wget https://www.python.org/ftp/python/3.6.3/Python-3.6.3.tar.xz
tar xJf Python-3.6.3.tar.xz
cd Python-3.6.3 && ./configure && make -j4 && make install
echo 'alias python3=python3.6' | sudo tee -a /home/pi/.bashrc

echo "  Prepare the python venv."
python3 -m venv $CURRENT_ANGELO_DIR/venv
echo "  Activate the python venv."
. $CURRENT_ANGELO_DIR/venv/bin/activate
echo "  Upgrade pip3."
pip3 install --upgrade pip

export CURRENT_ANGELO_DIR=${PWD}
export GST_BINARIES_DIR=/opt/psygig/gstreamer
echo "  Setting Angelo install dependencies to" $CURRENT_ANGELO_DIR
echo "  Setting gst binaries install to" $GST_BINARIES_DIR

FILE=$GST_BINARIES_DIR
if [ ! -d "$FILE" ]; then
    echo "  "$GST_BINARIES_DIR "directory doesn't exist, creating."
    mkdir -p $GST_BINARIES_DIR

    echo "  Downloading binaries."
    wget -nc https://psygig.bintray.com/PSYGIG/gstreamer-1.0-linux-arm-1.16.0.tar.bz2
    wget -nc https://psygig.bintray.com/PSYGIG/gstreamer-1.0-linux-arm-1.16.0-devel.tar.bz2
    wget -nc https://psygig.bintray.com/PSYGIG/gstreamer-1.0-linux-armhf-1.16.0-gst-python.tar.bz2

    echo "  Installing binaries."
    tar xvjf gstreamer-1.0-linux-arm-1.16.0.tar.bz2 -C $GST_BINARIES_DIR
    tar xvjf gstreamer-1.0-linux-arm-1.16.0-devel.tar.bz2 -C $GST_BINARIES_DIR
    tar xvjf gstreamer-1.0-linux-armhf-1.16.0-gst-python.tar.bz2 -C $GST_BINARIES_DIR
else
    echo $FILE "exists, skipping."
fi

echo "Setting up environment variables..."
FILE=$CURRENT_ANGELO_DIR/angelo.env
if [ ! -f "$FILE" ]; then
    echo "  angelo.env missing, creating."
    touch $CURRENT_ANGELO_DIR/angelo.env

    echo "  Updating environment variables."
    echo 'export LD_LIBRARY_PATH='$GST_BINARIES_DIR/lib:$LD_LIBRARY_PATH | sudo tee -a $CURRENT_ANGELO_DIR/angelo.env
    echo 'export PATH='$CURRENT_ANGELO_DIR/bin:$GST_BINARIES_DIR/bin:$PATH | sudo tee -a $CURRENT_ANGELO_DIR/angelo.env
    echo 'export PYTHONPATH='$CURRENT_ANGELO_DIR:$GST_BINARIES_DIR:$PYTHONPATH | sudo tee -a $CURRENT_ANGELO_DIR/angelo.env
    echo 'export GST_PLUGIN_PATH='$GST_BINARIES_DIR/lib/gstreamer-1.0:$GST_PLUGIN_PATH | sudo tee -a $CURRENT_ANGELO_DIR/angelo.env
    echo 'export ANGELO_PATH='$CURRENT_ANGELO_DIR | sudo tee -a $CURRENT_ANGELO_DIR/angelo.env

    echo 'source' $CURRENT_ANGELO_DIR/angelo.env | sudo tee -a /home/pi/.bashrc
else
    echo $FILE "exists, skipping." 
fi
. /home/pi/.bashrc

echo "Installing Angelo python dependencies..."
echo "  Install requirements."
pip3 install -r requirements.txt
echo 'source' $CURRENT_ANGELO_DIR/venv/bin/activate | sudo tee -a /home/pi/.bashrc
. /home/pi/.bashrc

echo "Installng rpicamsrc..."
echo "  Downloading rpicamsrc."
git clone https://github.com/thaytan/gst-rpicamsrc.git
echo "  Building rpicamsrc."
cd gst-rpicamsrc && ./autogen.sh --prefix=/usr --libdir=/usr/lib/arm-linux-gnueabihf/ && make -j4 && make install
echo "  Update install location."
cp /usr/lib/arm-linux-gnueabihf/gstreamer-1.0/libgstrpicamsrc.la /opt/psygig/gstreamer/lib/gstreamer-1.0/libgstrpicamsrc.la
cp /usr/lib/arm-linux-gnueabihf/gstreamer-1.0/libgstrpicamsrc.so /opt/psygig/gstreamer/lib/gstreamer-1.0/libgstrpicamsrc.so

echo "  Update libffi location."
mv /usr/lib/arm-linux-gnueabihf/libffi.so.6.0.4 /usr/lib/arm-linux-gnueabihf/libffi.so.6.0.4.bak
cp /opt/psygig/gstreamer/lib/libffi.so.7 /usr/lib/arm-linux-gnueabihf/libffi.so.6.0.4

echo "Post install cleanup..."
rm gstreamer-1.0-linux-arm-1.16.0.tar.bz2
rm gstreamer-1.0-linux-arm-1.16.0-devel.tar.bz2
rm gstreamer-1.0-linux-armhf-1.16.0-gst-python.tar.bz2

echo "Done."