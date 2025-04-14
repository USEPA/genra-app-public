FROM ghcr.io/usepa/python:latest

ARG PYVER=3.12
 
WORKDIR /genra

COPY requirements.txt /genra/

ARG GENRA_ARTIFACT_REPO
WORKDIR /root/.ssh
# COPY genra_artifact_key_* if they exist *without failing if not*,
# we know Dockerfile exists.
COPY Dockerfile genra_artifact_key_* ./
WORKDIR /
RUN if [ "${GENRA_ARTIFACT_REPO}" ]; then \
 chmod -R 600 ~/.ssh \
 && apt-get install -y git-lfs \
 && git lfs clone --depth 1 ${GENRA_ARTIFACT_REPO} /artifact_tar \
 && tar xaf /artifact_tar/artifacts.tar \
 && rm -rf /artifact_tar \
  ; fi 
RUN rm -rf ~/.ssh /Dockerfile
WORKDIR /genra

RUN apt-get --allow-releaseinfo-change update \
# libpq-dev needed for psycopg2 install
 && apt-get install -y libpq-dev \
 && pip install --upgrade pip --disable-pip-version-check \
 && pip install --upgrade -r requirements.txt \
 && pip freeze | grep -v ' @ ' > /requirements.txt.installed

# make this writable in container for automated tests
RUN mkdir /genra/karate_tests && chmod a+rw /genra/karate_tests \
 && if [ -e "/usr/lib/python${PYVER}/site-packages/jupyter_server" ]; then \
        INSTALL="/usr"; else INSTALL="/usr/local"; fi \
 && sed -i 's/input type="password"/input autocomplete="off" type="password"/g' \
    ${INSTALL}/lib/python${PYVER}/site-packages/jupyter_server/templates/login.html \
 && echo > ${INSTALL}/lib/python${PYVER}/site-packages/jupyter_server/templates/login.html
# Last two statements update and then redundantly remove the the /login page for
# jupyter lab - see uiJupyter endpoint for connection to Jupyter lab.

COPY . /genra

RUN chmod +x make_healthcheck_request.sh \
 && date '+%a %b %d %H:%M:%S %z %Y' > /.dockerbuild \
 && git config --global --add safe.directory /genra

HEALTHCHECK --interval=3s CMD ["bash", "./make_healthcheck_request.sh"]

CMD ["bash", "/genra/start.sh"]
