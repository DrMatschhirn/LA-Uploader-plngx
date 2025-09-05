
1. Dockerfile erstellen
docker build -t la-uploader:latest .

mkdir -p /root/uploader/jobs/{inbox,processing,done,failed,runs,samples}