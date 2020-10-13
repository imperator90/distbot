docker run -d --network host --init danielkelleher/distbot
docker run -it --network host --init danielkelleher/distbot python3 distbot/server.py -p 8000