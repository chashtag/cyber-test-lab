FROM fedora

RUN dnf install -y python-pip git vim gcc make patch ipython yum-utils hardening-check cpio findutils

RUN pip install python-magic

RUN cd /root && git clone https://github.com/chashtag/python-sdk.git && cd python-sdk && python3 setup.py install

RUN cd /root && git clone https://github.com/radare/radare2.git

RUN cd /root/radare2 && git checkout 4.3.0 && ./configure && make && make install

RUN pip install r2pipe timeout-decorator

RUN mkdir /fedora_swap
