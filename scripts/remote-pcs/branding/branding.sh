#!/bin/bash

################################################################################
# Branding functions
################################################################################

install_login_background() {
    local SOURCE="branding/Wall.png"
    local WALLPAPER_DIR="/usr/share/lubuntu/wallpapers"
    local LINK_NAME="/usr/share/sddm/themes/ubuntu-theme/wall.png"

    if [[ ! -f "$SOURCE" ]]; then
        echo "ERROR: $SOURCE not found."
        return 1
    fi

    echo "Installing login background..."

    install -m 644 -o root -g root \
        "$SOURCE" \
        "$WALLPAPER_DIR/Wall.png"

    ln -sfn \
        "$WALLPAPER_DIR/Wall.png" \
        "$LINK_NAME"

    echo "✓ Login background installed."
}
