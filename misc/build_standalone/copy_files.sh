
TIMESTAMP=$(date +%Y%m%d%M%H%S)
DIR=standalone$TIMESTAMP
mkdir $DIR
echo "Copying files to $DIR"
SRC=misc/build_standalone
cp $SRC/README.md $DIR
cp $SRC/httpd.conf $DIR
cp $SRC/docker-compose-standalone.yml $DIR/docker-compose.yml
cp $SRC/standalone.env $DIR


