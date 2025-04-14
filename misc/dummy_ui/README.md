# Dummy UI, no longer used

This folder contains a dummy UI originally used to test connectivity to API, no
longer needed.  To use it, put the service definition below back in
`docker-compose.yml`.

```Dockerfile
  genra_ui:
    env_file:
      - genra_settings.env
    ports:
      - ${EXT_GENRA_UI_PORT}:8000
    build:
      context: misc/dummy_ui
      args:
        EXT_GENRA_API_URL: ${EXT_GENRA_API_URL}
```
