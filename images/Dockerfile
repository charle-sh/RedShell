FROM alpine
RUN apk add --no-cache openssh sshpass python3 py3-pip proxychains-ng freerdp
RUN pip3 install impacket
RUN wget https://github.com/carlospolop/PEASS-ng/releases/latest/download/linpeas.sh
RUN mv linpeas.sh /linpeas.sh
COPY ./config /root/.ssh/config
RUN chmod 600 /root/.ssh/config
COPY ./proxychains.conf /etc/proxychains/proxychains.conf
ENV DISPLAY :0
WORKDIR /data