#!/bin/bash

echo "Adding services & routes to ${KONG_URL}..."

# Hostnames
USER_HOST="user-api.agendable.local"
MEETING_HOST="meeting-api.agendable.local"
UI_HOST="web-ui.agendable.local"

# Helper Functions
create_service() {
    local SERVICE_NAME=$1
    local SERVICE_URL=$2

    SERVICE_EXISTS=$(/usr/bin/curl -s ${KONG_URL}/services/$SERVICE_NAME | /usr/bin/jq -r '.name')
    if [ "$SERVICE_EXISTS" != "$SERVICE_NAME" ]; then
        echo "Creating $SERVICE_NAME..."
        /usr/bin/curl -i -X POST \
            --url ${KONG_URL}/services/ \
            --data "name=$SERVICE_NAME" \
            --data "url=$SERVICE_URL"
    else
        echo "Service $SERVICE_NAME already exists."
    fi
}

create_route() {
    local SERVICE_NAME=$1
    local ROUTE_NAME=$2
    local HOSTNAME=$3

    ROUTE_EXISTS=$(/usr/bin/curl -s ${KONG_URL}/routes/$ROUTE_NAME | jq -r '.name')
    if [ "$ROUTE_EXISTS" != "$ROUTE_NAME" ]; then
        echo "Creating host‐based route $ROUTE_NAME for $HOSTNAME..."
        /usr/bin/curl -i -X POST \
            --url ${KONG_URL}/services/$SERVICE_NAME/routes \
            --data "name=$ROUTE_NAME" \
            --data "hosts[]=$HOSTNAME" \
            --data "strip_path=false" \
            --data "preserve_host=true"
    else
        echo "Route $ROUTE_NAME already exists."
    fi
}

enable_plugin() {
    local SERVICE_NAME=$1
    local PLUGIN_NAME=$2
    shift 2
    local PLUGIN_CONFIG=$@

    PLUGIN_EXISTS=$(/usr/bin/curl -s ${KONG_URL}/services/$SERVICE_NAME/plugins | /usr/bin/jq -r ".data[] | select(.name==\"$PLUGIN_NAME\") | .name")
    if [ "$PLUGIN_EXISTS" != "$PLUGIN_NAME" ]; then
        echo "Enabling $PLUGIN_NAME Plugin for $SERVICE_NAME..."
        /usr/bin/curl -i -X POST \
            --url ${KONG_URL}/services/$SERVICE_NAME/plugins/ \
            --data "name=$PLUGIN_NAME" $PLUGIN_CONFIG
    else
        echo "$PLUGIN_NAME Plugin already enabled for $SERVICE_NAME."
    fi
}

create_consumer() {
    local CONSUMER_NAME=$1

    CONSUMER_EXISTS=$(/usr/bin/curl -s ${KONG_URL}/consumers/$CONSUMER_NAME | /usr/bin/jq -r '.username')
    if [ "$CONSUMER_EXISTS" != "$CONSUMER_NAME" ]; then
        echo "Creating consumer $CONSUMER_NAME..."
        /usr/bin/curl -i -X POST \
            --url ${KONG_URL}/consumers/ \
            --data "username=$CONSUMER_NAME"
    else
        echo "Consumer $CONSUMER_NAME already exists."
    fi
}

associate_jwt() {
    local CONSUMER_NAME=$1
    local JWT_KEY=$2
    local JWT_SECRET=$3

    JWT_EXISTS=$(/usr/bin/curl -s ${KONG_URL}/consumers/$CONSUMER_NAME/jwt | /usr/bin/jq -r ".data[] | select(.key==\"$JWT_KEY\") | .key")
    if [ "$JWT_EXISTS" != "$JWT_KEY" ]; then
        echo "Associating JWT with consumer $CONSUMER_NAME..."
        /usr/bin/curl -i -X POST \
            --url ${KONG_URL}/consumers/$CONSUMER_NAME/jwt/ \
            --data "key=$JWT_KEY" \
            --data "algorithm=HS256" \
            --data "secret=$JWT_SECRET"
    else
        echo "JWT already associated with $CONSUMER_NAME."
    fi
}

# 1) Services
create_service "user-service"    "http://user-service:8004"
create_service "meeting-service" "http://meeting-service:8005"
create_service "web-ui"          "http://web-ui:8002"

# 2) Host‐based routes
create_route "user-service"    "user-service-route"    "$USER_HOST"
create_route "meeting-service" "meeting-service-route" "$MEETING_HOST"
create_route "web-ui"          "web-ui-route"          "$UI_HOST"
