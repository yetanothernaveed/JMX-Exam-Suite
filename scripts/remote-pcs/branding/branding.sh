#!/bin/bash

################################################################################
# Branding functions
################################################################################

# install_login_background() {
#     local SOURCE="branding/Wall.png"
#     local WALLPAPER_DIR="/usr/share/lubuntu/wallpapers"
#     local LINK_NAME="/usr/share/sddm/themes/ubuntu-theme/wall.png"

#     if [[ ! -f "$SOURCE" ]]; then
#         echo "ERROR: $SOURCE not found."
#         return 1
#     fi

#     echo "Installing login background..."

#     install -m 644 -o root -g root \
#         "$SOURCE" \
#         "$WALLPAPER_DIR/Wall.png"

#     ln -sfn \
#         "$WALLPAPER_DIR/Wall.png" \
#         "$LINK_NAME"

#     echo "✓ Login background installed."
# }

install_login_background() {
    local SOURCE="branding/AustereWall.png"
    local DEST="/usr/share/lubuntu/wallpapers/exam-wallpaper.png"
    local LUBUNTU_THEME_CONF="/usr/share/sddm/themes/lubuntu/theme.conf"

    if [[ ! -f "$SOURCE" ]]; then
        echo "ERROR: $SOURCE not found."
        return 1
    fi

    echo "Installing login background..."

    # 1. Copy the image to a global location accessible by SDDM
    sudo install -m 644 -o root -g root "$SOURCE" "$DEST"

    # 2. Update the Lubuntu SDDM theme to point directly to our new image
    if [[ -f "$LUBUNTU_THEME_CONF" ]]; then
        sudo sed -i 's|^background=.*|background='"$DEST"'|' "$LUBUNTU_THEME_CONF"
    else
        echo "WARNING: Lubuntu theme config not found at $LUBUNTU_THEME_CONF"
        # Fallback to standard ubuntu-theme if lubuntu isn't present
        local FALLBACK_CONF="/usr/share/sddm/themes/ubuntu-theme/theme.conf"
        if [[ -f "$FALLBACK_CONF" ]]; then
            sudo sed -i 's|^background=.*|background='"$DEST"'|' "$FALLBACK_CONF"
        fi
    fi

    echo "✓ Login background installed."
}

install_plymouth_branding() {
    local SOURCE_IMG="branding/AustereWall.png"
    local THEME_NAME="examkiosk"
    local THEME_DIR="/usr/share/plymouth/themes/$THEME_NAME"

    if [[ ! -f "$SOURCE_IMG" ]]; then
        echo "ERROR: $SOURCE_IMG not found. Skipping boot screen setup."
        return 1
    fi

    echo "Installing custom boot screen (this may take a moment)..."

    # 1. Create the Plymouth theme directory
    mkdir -p "$THEME_DIR"

    # 2. Copy your custom splash image
    cp "$SOURCE_IMG" "$THEME_DIR/splash.png"
    chmod 644 "$THEME_DIR/splash.png"

    # 3. Create the configuration file (.plymouth)
    cat << EOF > "$THEME_DIR/$THEME_NAME.plymouth"
[Plymouth Theme]
Name=ExamKiosk
Description=Custom Boot Screen for Exam Kiosk
ModuleName=script

[script]
ImageDir=$THEME_DIR
ScriptFile=$THEME_DIR/$THEME_NAME.script
EOF

    # 4. Create a simple script to center and correctly scale the image on any monitor
    cat << 'EOF' > "$THEME_DIR/$THEME_NAME.script"
image = Image("splash.png");

# Calculate aspect ratio to perfectly fit the screen
screen_ratio = Window.GetHeight() / Window.GetWidth();
image_ratio = image.GetHeight() / image.GetWidth();

if (screen_ratio > image_ratio) {
  scale_factor = Window.GetHeight() / image.GetHeight();
} else {
  scale_factor = Window.GetWidth() / image.GetWidth();
}

scaled_image = image.Scale(image.GetWidth() * scale_factor, image.GetHeight() * scale_factor);
sprite = Sprite(scaled_image);

# Center the image
sprite.SetX(Window.GetWidth() / 2 - scaled_image.GetWidth() / 2);
sprite.SetY(Window.GetHeight() / 2 - scaled_image.GetHeight() / 2);
EOF

    # 5. Register the new theme with Ubuntu's alternatives system
    update-alternatives --install /usr/share/plymouth/themes/default.plymouth default.plymouth "$THEME_DIR/$THEME_NAME.plymouth" 100
    
    # 6. Set it as the default theme
    update-alternatives --set default.plymouth "$THEME_DIR/$THEME_NAME.plymouth"

    # 7. Rebuild the initial ramdisk so the image is loaded during early boot
    echo "Updating initramfs to apply boot screen..."
    update-initramfs -u

    echo "✓ Custom boot screen installed."
}

################################################################################
# GRUB configuration
################################################################################

GRUB_CONFIG_FILE="/etc/default/grub"
GRUB_GENERATED_CONFIG="/boot/grub/grub.cfg"

# Keep one pristine copy of the distro defaults before our edits.
backup_grub_config() {
    if [ ! -f "${GRUB_CONFIG_FILE}.jmx.bak" ]; then
        sudo cp -a "$GRUB_CONFIG_FILE" "${GRUB_CONFIG_FILE}.jmx.bak"
        echo "Backed up $GRUB_CONFIG_FILE to ${GRUB_CONFIG_FILE}.jmx.bak"
    fi
}

# Set a KEY=value line in /etc/default/grub without disturbing other settings.
# Handles commented-out keys (e.g. #GRUB_DISABLE_OS_PROBER=false) and appends
# keys that are not present at all.
set_grub_value() {
    local key="$1"
    local value="$2"

    if sudo grep -qE "^[[:space:]]*#?[[:space:]]*${key}=" "$GRUB_CONFIG_FILE"; then
        sudo sed -i -E "s|^[[:space:]]*#?[[:space:]]*${key}=.*|${key}=${value}|" "$GRUB_CONFIG_FILE"
    else
        printf '%s=%s\n' "$key" "$value" | sudo tee -a "$GRUB_CONFIG_FILE" >/dev/null
    fi
}

install_grub_branding() {
    backup_grub_config

    # /etc/grub.d/10_linux takes the menu entry titles from GRUB_DISTRIBUTOR,
    # so "Ubuntu" entries become "JMX OS" after the config is regenerated.
    set_grub_value GRUB_DISTRIBUTOR '"JMX OS"'
    sudo update-grub

    echo "✓ GRUB menu entries renamed to JMX OS."
}

configure_grub_default_os() {
    backup_grub_config

    # os-prober is disabled by default on current Ubuntu, so Windows would not
    # appear in the menu at all unless it is installed and explicitly enabled.
    if ! command -v os-prober >/dev/null 2>&1; then
        sudo apt-get install -y os-prober ||
            echo "WARNING: could not install os-prober; Windows detection skipped"
    fi
    set_grub_value GRUB_DISABLE_OS_PROBER 'false'
    sudo update-grub

    # Target the generated entry id instead of a menu index: kernel updates
    # change indices and titles, but the Windows prober id stays the same.
    local windows_id
    windows_id=$(
        { sudo grep -i -m1 'menuentry.*windows' "$GRUB_GENERATED_CONFIG" || true; } |
        sed -nE "s/.*\\\$menuentry_id_option '([^']+)'.*/\1/p"
    )

    if [ -n "$windows_id" ]; then
        # GRUB_DEFAULT=saved has to be in grub.cfg before grub-set-default
        # writes the chosen id to /boot/grub/grubenv.
        set_grub_value GRUB_DEFAULT 'saved'
        set_grub_value GRUB_SAVEDEFAULT 'false'
        sudo update-grub
        if sudo grub-set-default "$windows_id"; then
            echo "✓ Windows is the default GRUB entry ($windows_id)."
        else
            echo "WARNING: could not save Windows as the GRUB default entry"
        fi
    else
        # Clear a saved entry left over from a Windows install that is gone.
        set_grub_value GRUB_DEFAULT '0'
        sudo grub-editenv /boot/grub/grubenv unset saved_entry 2>/dev/null || true
        sudo update-grub
        echo "No Windows entry found; keeping the first GRUB entry as default."
    fi
}
