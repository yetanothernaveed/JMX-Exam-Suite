#!/bin/bash
set -e

echo ">>> [1/8] Installing system dependencies..."
sudo apt update
sudo apt install -y build-essential python3 openjdk-21-jdk openbox firejail

echo ">>> [2/8] Installing VS Code..."
sudo apt-get install -y wget gpg
wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
sudo install -D -o root -g root -m 644 packages.microsoft.gpg /etc/apt/keyrings/packages.microsoft.gpg
sudo sh -c 'echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list'
rm -f packages.microsoft.gpg
sudo apt update && sudo apt install -y code

echo ">>> [3/8] Creating examkiosk user and workspace..."
sudo adduser --disabled-password --gecos "" examkiosk

# Prompt for password at runtime instead of hardcoding it
echo "Set password for examkiosk user:"
sudo passwd examkiosk

sudo mkdir -p /home/examkiosk/exam_workspace
sudo chown examkiosk:examkiosk /home/examkiosk/exam_workspace
sudo chmod 700 /home/examkiosk/exam_workspace

echo ">>> [4/8] Setting up VS Code config directories and installing extensions..."
sudo mkdir -p /home/examkiosk/.config/Code/User
sudo mkdir -p /home/examkiosk/.vscode
sudo chown -R examkiosk:examkiosk /home/examkiosk/.vscode
sudo chown -R examkiosk:examkiosk /home/examkiosk/.config/Code
sudo chmod -R 755 /home/examkiosk/.vscode
sudo chmod -R 755 /home/examkiosk/.config/Code

# Install extensions now that directories are ready
sudo -u examkiosk code --install-extension vscjava.vscode-java-pack
sudo -u examkiosk code --install-extension ms-python.python
sudo -u examkiosk code --install-extension ms-vscode.cpptools

echo ">>> [5/8] Writing VS Code settings..."
cat << 'EOF' > /tmp/vscode-settings.json
{
    "update.mode": "none",
    "telemetry.telemetryLevel": "off",
    "workbench.statusBar.visible": true,
    "extensions.autoUpdate": false,
    "java.home": "/usr/lib/jvm/java-21-openjdk-amd64",
    "files.autoSave": "afterDelay",
    "files.autoSaveDelay": 1000,
    "window.titleBarStyle": "native",
    "workbench.activityBar.location": "hidden"
}
EOF
sudo mv /tmp/vscode-settings.json /home/examkiosk/.config/Code/User/settings.json

echo ">>> [6/8] Writing exam session launch script..."
TMP_SCRIPT="/tmp/exam-session.sh"
DEST="/usr/local/bin/exam-session.sh"

cat << 'EOF' > "$TMP_SCRIPT"
#!/bin/bash

# Start Openbox window manager and wait for it to be ready
openbox-session &
OPENBOX_PID=$!
sleep 2

# Launch VS Code inside Firejail
firejail --net=none \
  --whitelist=/home/examkiosk/exam_workspace \
  --whitelist=/home/examkiosk/.vscode/extensions \
  --whitelist=/home/examkiosk/.config/Code \
  --whitelist=/home/examkiosk/.bashrc \
  code --kiosk --wait /home/examkiosk/exam_workspace

# When VS Code is closed, kill Openbox and log out
kill $OPENBOX_PID
killall openbox 2>/dev/null || true
EOF

sudo mv "$TMP_SCRIPT" "$DEST"
sudo chmod +x /usr/local/bin/exam-session.sh

echo ">>> [7/8] Registering exam session with display manager and installing Openbox config..."
TMP_DESKTOP="/tmp/exam.desktop"
DEST_DESKTOP="/usr/share/xsessions/exam.desktop"

cat << 'EOF' > "$TMP_DESKTOP"
[Desktop Entry]
Name=Exam Environment
Comment=Secure VS Code Exam Kiosk
Exec=/usr/local/bin/exam-session.sh
Type=Application
EOF

sudo mv "$TMP_DESKTOP" "$DEST_DESKTOP"

sudo mkdir -p /home/examkiosk/.config/openbox
sudo mv rc.xml /home/examkiosk/.config/openbox/

echo ">>> [8/8] Locking down permissions..."
# Run VS Code once (headless) to ensure extension file structure is initialised
sudo -u examkiosk code --list-extensions

# Lock down config files - read-only for examkiosk, owned by root
sudo chown root:root /home/examkiosk/.config/Code/User/settings.json
sudo chmod 644 /home/examkiosk/.config/Code/User/settings.json
sudo chown -R root:root /home/examkiosk/.vscode/extensions
sudo chmod 755 /home/examkiosk/.vscode/extensions

# Disabled for testing stage. Enable before final setup
# echo ">>> [Extra] Deleting all other desktop environments"
# sudo find /usr/share/xsessions/ -name "*.desktop" ! -name "exam.desktop" -delete

echo ">>> Exam kiosk setup complete."
