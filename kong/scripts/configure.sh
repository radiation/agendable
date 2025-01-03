#!/bin/bash

echo "Adding services & routes to ${KONG_URL}..."

################
# User Service #
################

# Check if the User Service exists
SERVICE_EXISTS=$(/usr/bin/curl -s ${KONG_URL}/services/user-service | /usr/bin/jq -r '.name')
if [ "$SERVICE_EXISTS" != "user-service" ]; then
    echo "Creating user-service..."
    /usr/bin/curl -i -X POST \
        --url ${KONG_URL}/services/ \
        --data 'name=user-service' \
        --data 'url=http://user-service:8004'
else
    echo "Service user-service already exists."
fi

# Check and create routes for the User Service
ROUTES=("user-service_docs:/docs" "auth_route:/auth" "users_route:/users" "openapi_json:/openapi.json")
for ROUTE in "${ROUTES[@]}"; do
    NAME=$(echo "$ROUTE" | /usr/bin/cut -d':' -f1)
    PATH=$(echo "$ROUTE" | /usr/bin/cut -d':' -f2)

    ROUTE_EXISTS=$(/usr/bin/curl -s ${KONG_URL}/routes/$NAME | /usr/bin/jq -r '.name')
    if [ "$ROUTE_EXISTS" != "$NAME" ]; then
        echo "Creating route $NAME..."
        /usr/bin/curl -i -X POST \
            --url ${KONG_URL}/services/user-service/routes \
            --data "name=$NAME" \
            --data "paths[]=$PATH" \
            --data 'strip_path=false'
    else
        echo "Route $NAME already exists."
    fi
done

###################
# Meeting Service #
###################

# Check if the Meeting Service exists
SERVICE_EXISTS=$(/usr/bin/curl -s ${KONG_URL}/services/meeting-service | /usr/bin/jq -r '.name')
if [ "$SERVICE_EXISTS" != "meeting-service" ]; then
    echo "Creating meeting-service..."
    /usr/bin/curl -i -X POST \
        --url ${KONG_URL}/services/ \
        --data 'name=meeting-service' \
        --data 'url=http://meeting-service:8005'
else
    echo "Service meeting-service already exists."
fi

# Check and create routes for the Meeting Service
ROUTES=("meeting-service_docs:/docs" "meetings_route:/meetings" \
        "recurrences_route:/meeting_recurrences" "attendees_route:/meeting_attendees" \
        "tasks_route:/tasks" "meeting_tasks_route:/meeting_tasks" "openapi_json:/openapi.json")
for ROUTE in "${ROUTES[@]}"; do
    NAME=$(echo "$ROUTE" | /usr/bin/cut -d':' -f1)
    PATH=$(echo "$ROUTE" | /usr/bin/cut -d':' -f2)

    ROUTE_EXISTS=$(/usr/bin/curl -s ${KONG_URL}/routes/$NAME | /usr/bin/jq -r '.name')
    if [ "$ROUTE_EXISTS" != "$NAME" ]; then
        echo "Creating route $NAME..."
        /usr/bin/curl -i -X POST \
            --url ${KONG_URL}/services/meeting-service/routes \
            --data "name=$NAME" \
            --data "paths[]=$PATH" \
            --data 'strip_path=false'
    else
        echo "Route $NAME already exists."
    fi
done

# Enable JWT Plugin for Meeting Service
PLUGIN_EXISTS=$(/usr/bin/curl -s ${KONG_URL}/services/meeting-service/plugins | /usr/bin/jq -r '.data[] | select(.name=="jwt") | .name')
if [ "$PLUGIN_EXISTS" != "jwt" ]; then
    echo "Enabling JWT Plugin for meeting-service..."
    /usr/bin/curl -i -X POST \
        --url ${KONG_URL}/services/meeting-service/plugins/ \
        --data "name=jwt" \
        --data "config.claims_to_verify=exp" \
        --data "config.key_claim_name=iss" \
        --data "config.secret_is_base64=false"
else
    echo "JWT Plugin already enabled for meeting-service."
fi

# Check and add a Consumer
CONSUMER_EXISTS=$(/usr/bin/curl -s ${KONG_URL}/consumers/user-service-consumer | /usr/bin/jq -r '.username')
if [ "$CONSUMER_EXISTS" != "user-service-consumer" ]; then
    echo "Creating consumer user-service-consumer..."
    /usr/bin/curl -i -X POST \
        --url ${KONG_URL}/consumers/ \
        --data "username=user-service-consumer"
else
    echo "Consumer user-service-consumer already exists."
fi

# Check and associate JWT with the Consumer
JWT_EXISTS=$(/usr/bin/curl -s ${KONG_URL}/consumers/user-service-consumer/jwt | /usr/bin/jq -r '.data[] | select(.key=="user-service") | .key')
echo "SECRET_KEY: ${SECRET_KEY}"
if [ "$JWT_EXISTS" != "user-service" ]; then
    echo "Associating JWT with consumer user-service-consumer..."
    /usr/bin/curl -i -X POST \
        --url ${KONG_URL}/consumers/user-service-consumer/jwt/ \
        --data "key=user-service" \
        --data "algorithm=HS256" \
        --data "secret=${SECRET_KEY}"
else
    echo "JWT already associated with user-service-consumer."
fi

# Enable request-transformer Plugin for Meeting Service
PLUGIN_EXISTS=$(/usr/bin/curl -s ${KONG_URL}/services/meeting-service/plugins | /usr/bin/jq -r '.data[] | select(.name=="request-transformer") | .name')
if [ "$PLUGIN_EXISTS" != "request-transformer" ]; then
    echo "Enabling request-transformer Plugin for meeting-service..."
    /usr/bin/curl -i -X POST \
        --url ${KONG_URL}/services/meeting-service/plugins/ \
        --data "name=request-transformer" \
        --data "config.add.headers=X-User-ID:\$claims.sub,X-User-Email:\$claims.email"
else
    echo "request-transformer Plugin already enabled for meeting-service."
fi

###############
# CORS Plugin #
###############

# Enable CORS Plugin for Meeting Service
PLUGIN_EXISTS=$(/usr/bin/curl -s ${KONG_URL}/services/meeting-service/plugins | /usr/bin/jq -r '.data[] | select(.name=="cors") | .name')
if [ "$PLUGIN_EXISTS" != "cors" ]; then
    echo "Enabling CORS Plugin for meeting-service..."
    /usr/bin/curl -i -X POST \
        --url ${KONG_URL}/services/meeting-service/plugins/ \
        --data "name=cors" \
        --data "config.origins=*" \
        --data "config.methods[]=GET" \
        --data "config.methods[]=HEAD" \
        --data "config.methods[]=PUT" \
        --data "config.methods[]=PATCH" \
        --data "config.methods[]=POST" \
        --data "config.methods[]=DELETE" \
        --data "config.methods[]=OPTIONS" \
        --data "config.headers[]=Content-Type" \
        --data "config.headers[]=Authorization" \
        --data "config.exposed_headers[]=Authorization" \
        --data "config.credentials=true"
else
    echo "CORS Plugin already enabled for meeting-service."
fi

# Enable CORS Plugin for User Service
PLUGIN_EXISTS=$(/usr/bin/curl -s ${KONG_URL}/services/user-service/plugins | /usr/bin/jq -r '.data[] | select(.name=="cors") | .name')
if [ "$PLUGIN_EXISTS" != "cors" ]; then
    echo "Enabling CORS Plugin for user-service..."
    /usr/bin/curl -i -X POST \
        --url ${KONG_URL}/services/user-service/plugins/ \
        --data "name=cors" \
        --data "config.origins=*" \
        --data "config.methods[]=GET" \
        --data "config.methods[]=HEAD" \
        --data "config.methods[]=PUT" \
        --data "config.methods[]=PATCH" \
        --data "config.methods[]=POST" \
        --data "config.methods[]=DELETE" \
        --data "config.methods[]=OPTIONS" \
        --data "config.headers[]=Content-Type" \
        --data "config.headers[]=Authorization" \
        --data "config.exposed_headers[]=Authorization" \
        --data "config.credentials=true"
else
    echo "CORS Plugin already enabled for user-service."
fi
