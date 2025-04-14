HEALTHCHECK_RESPONSE=$(curl -s --request GET "${GENRA_API_URL}/api/genra/v3/healthCheck/")
SUCCESS_MESSAGE="HEALTHY"
if [[ ${HEALTHCHECK_RESPONSE} == *"${SUCCESS_MESSAGE}"* ]]; then
    echo "Docker healthcheck success"
    exit 0
else
    echo "Docker healthcheck fail"
    exit 1
fi
