#!/bin/sh
# This script launches ETH2 validator clients for Rocket Pool's docker stack; only edit if you know what you're doing ;)


# RP version number for graffiti; MAX 10 chars
ROCKET_POOL_VERSION="v1.0.0-b.1"


# Get graffiti text
GRAFFITI="RP $ROCKET_POOL_VERSION"
if [ ! -z "$CUSTOM_GRAFFITI" ]; then
    GRAFFITI="$GRAFFITI ($CUSTOM_GRAFFITI)"
fi


# Lighthouse startup
if [ "$CLIENT" = "lighthouse" ]; then

    exec /usr/local/bin/lighthouse validator --network pyrmont --datadir /data/validators/lighthouse --init-slashing-protection --beacon-node "http://$ETH2_PROVIDER" --graffiti-file /data/graffiti.txt

fi


# Nimbus startup
if [ "$CLIENT" = "nimbus" ]; then

    # Do nothing since the validator is built into the beacon client
    trap 'kill -9 $sleep_pid' INT TERM
    sleep infinity &
    sleep_pid=$!
    wait

fi


# Prysm startup
if [ "$CLIENT" = "prysm" ]; then

    exec /app/cmd/validator/validator --accept-terms-of-use --pyrmont --wallet-dir /data/validators/prysm-non-hd --wallet-password-file /data/password --beacon-rpc-provider "$ETH2_PROVIDER" --graffiti-file /data/graffiti.txt

fi


# Teku startup
if [ "$CLIENT" = "teku" ]; then

    exec /opt/teku/bin/teku validator-client --network=pyrmont --validator-keys=/data/validators/teku/keys:/data/validators/teku/passwords --beacon-node-api-endpoint="http://$ETH2_PROVIDER" --validators-graffiti-file=/data/graffiti.txt

fi

