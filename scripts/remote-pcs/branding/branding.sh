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
    local SOURCE="branding/Wall.png"
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
    local SOURCE_IMG="branding/Banner.png"
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
