FROM python

ARG EXT_GENRA_API_URL

WORKDIR /ui

RUN git clone https://github.com/abodelot/jquery.json-viewer

COPY . /ui

RUN sed -i 's|{{EXT_GENRA_API_URL}}|'${EXT_GENRA_API_URL}'|g' index.html

CMD ["python", "-m", "http.server"]
