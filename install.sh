echo "Installing Angelo gstreamer dependencies..."
sudo apt-get install libglib2.0-dev libgirepository1.0-dev libcairo2-dev python3-venv 

export CURRENT_ANGELO_DIR=${PWD}
export GST_BINARIES_DIR=/opt/psygig/gstreamer
echo "  Installing Angelo dependencies to" $CURRENT_ANGELO_DIR
echo "  Installing gst binaries to" $GST_BINARIES_DIR

FILE=$GST_BINARIES_DIR
if [ ! -d "$FILE" ]; then
    mkdir -p $GST_BINARIES_DIR

    wget -nc https://psygig.bintray.com/PSYGIG/gstreamer-1.0-linux-arm-1.16.0.tar.bz2
    wget -nc https://psygig.bintray.com/PSYGIG/gstreamer-1.0-linux-arm-1.16.0-devel.tar.bz2
    wget -nc https://psygig.bintray.com/PSYGIG/gstreamer-1.0-linux-armhf-1.16.0-gst-python.tar.bz2

    tar xvjf gstreamer-1.0-linux-arm-1.16.0.tar.bz2 -C $GST_BINARIES_DIR
    tar xvjf gstreamer-1.0-linux-arm-1.16.0-devel.tar.bz2 -C $GST_BINARIES_DIR
    tar xvjf gstreamer-1.0-linux-armhf-1.16.0-gst-python.tar.bz2 -C $GST_BINARIES_DIR
fi

echo "Setting up environment variables..."
FILE=$CURRENT_ANGELO_DIR/angelo.env
if [ ! -f "$FILE" ]; then
    touch $CURRENT_ANGELO_DIR/angelo.env

    echo "  Preparing to add" $GST_BINARIES_DIR/lib "to LD_LIBRARY_PATH"
    echo 'export LD_LIBRARY_PATH='$GST_BINARIES_DIR/lib:$LD_LIBRARY_PATH | sudo tee -a $CURRENT_ANGELO_DIR/angelo.env

    echo "  Preparing to add" $CURRENT_ANGELO_DIR/bin:$GST_BINARIES_DIR/bin "to PATH"
    echo 'export PATH='$CURRENT_ANGELO_DIR/bin:$GST_BINARIES_DIR/bin:$PATH | sudo tee -a $CURRENT_ANGELO_DIR/angelo.env

    echo "  Preparing to add" $CURRENT_ANGELO_DIR:$GST_BINARIES_DIR "to PYTHONPATH"
    echo 'export PYTHONPATH='$CURRENT_ANGELO_DIR:$GST_BINARIES_DIR:$PYTHONPATH | sudo tee -a $CURRENT_ANGELO_DIR/angelo.env

    echo "  Preparing to add" $GST_BINARIES_DIR/lib/gstreamer-1.0 "to GST_PLUGIN_PATH"
    echo 'export GST_PLUGIN_PATH='$GST_BINARIES_DIR/lib/gstreamer-1.0:$GST_PLUGIN_PATH | sudo tee -a $CURRENT_ANGELO_DIR/angelo.env

    echo "  Preparing to add" $CURRENT_ANGELO_DIR "to ANGELO_PATH"
    echo 'export ANGELO_PATH='$CURRENT_ANGELO_DIR | sudo tee -a $CURRENT_ANGELO_DIR/angelo.env

    echo 'source' $CURRENT_ANGELO_DIR/angelo.env | sudo tee -a /home/pi/.bashrc
fi
. /home/pi/.bashrc

echo "Installing Angelo python dependencies..."
echo "  Prepare the python venv"
python3 -m venv $CURRENT_ANGELO_DIR/venv
echo "  Activate the python venv"
. $CURRENT_ANGELO_DIR/venv/bin/activate
echo "  Upgrade pip3"
pip3 install --upgrade pip
echo "  Install requirements"
pip3 install -r requirements.txt
echo 'source' $CURRENT_ANGELO_DIR/venv/bin/activate | sudo tee -a /home/pi/.bashrc

echo "Installng rpicamsrc"
apt-get install autoconf automake libtool pkg-config libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libraspberrypi-dev -y
git clone https://github.com/thaytan/gst-rpicamsrc.git
cd gst-rpicamsrc && ./autogen.sh --prefix=/usr --libdir=/usr/lib/arm-linux-gnueabihf/ && make -j4 && make install
cp /usr/lib/arm-linux-gnueabihf/gstreamer-1.0/libgstrpicamsrc.la /opt/psygig/gstreamer/lib/gstreamer-1.0/libgstrpicamsrc.la
cp /usr/lib/arm-linux-gnueabihf/gstreamer-1.0/libgstrpicamsrc.so /opt/psygig/gstreamer/lib/gstreamer-1.0/libgstrpicamsrc.so

echo "Post install cleanup..."
rm gstreamer-1.0-linux-arm-1.16.0.tar.bz2
rm gstreamer-1.0-linux-arm-1.16.0-devel.tar.bz2
rm gstreamer-1.0-linux-armhf-1.16.0-gst-python.tar.bz2
echo "Done."