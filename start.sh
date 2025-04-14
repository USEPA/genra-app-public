# This is the script used by Docker CMD to start the API server.

. ~/.bashrc
date '+%a %b %d %H:%M:%S %z %Y' > /.dockerrun
if [[ "$GENRA_DEPLOYMENT_TYPE" == *"LOCAL"* ]]; then 
    jupyter lab --ip 0.0.0.0 --allow-root &
fi
if [[ "$GENRA_CELERY_IN_GENRA" ]]; then
    # Keep this in sync with the celery command in docker-compose-worker.yml.template
    celery -A genraweb.genra_celery worker -l INFO &
fi
gunicorn genraweb.genra_flask:app
