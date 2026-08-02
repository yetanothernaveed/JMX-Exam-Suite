#!/bin/bash
set -e

echo ">>> [1] Load custom branding..."
source branding/branding.sh

echo ">>> [2] Installing system dependencies..."
sudo apt update
sudo apt install -y build-essential python3 openjdk-21-jdk openbox firejail sqlite3 libsqlite3-dev

echo ">>> [3] Installing VS Code..."
sudo apt-get install -y wget gpg
wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
sudo install -D -o root -g root -m 644 packages.microsoft.gpg /etc/apt/keyrings/packages.microsoft.gpg
sudo sh -c 'echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list'
rm -f packages.microsoft.gpg
sudo apt update && sudo apt install -y code

echo ">>> [4] Creating examkiosk user and workspace..."
if ! id examkiosk &>/dev/null; then
    adduser --disabled-password --gecos "" examkiosk
fi

EXAMKIOSK_PASSWORD="2304"
echo "examkiosk:${EXAMKIOSK_PASSWORD}" | chpasswd

mkdir -p /home/examkiosk/exam_workspace
chown examkiosk:examkiosk /home/examkiosk/exam_workspace
chmod 700 /home/examkiosk/exam_workspace

echo ">>> [5] Creating new user group jmx and adding user examkiosk to the jmx group"
getent group jmx >/dev/null || groupadd --system jmx
sudo usermod -aG jmx examkiosk

echo ">>> [6] Setting up VS Code config directories and installing extensions..."
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

echo ">>> [7] Writing VS Code settings and keybindings..."

# 1. Write settings.json (Added UI lockdown settings and fixed missing comma)
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
    "workbench.activityBar.location": "hidden",
    "window.menuBarVisibility": "none",
    "window.commandCenter": false,
    "workbench.layoutControl.enabled": false,
    "security.workspace.trust.enabled": false,
    "chat.disableAIFeatures": true,
    "github.copilot.enable": {
        "*": false
    },
    "github.copilot.editor.enableCodeActions": false,
    "github.copilot.nextEditSuggestions.enabled": false,
    "editor.inlineSuggestions.edits.allowCodeShifting": "never",
    
    "terminal.integrated.shellIntegration.enabled": false,
    "terminal.integrated.defaultProfile.linux": "RestrictedBash",
    "terminal.integrated.automationProfile.linux": {
        "path": "/bin/bash",
        "args": ["--noprofile", "--restricted", "--rcfile", "/home/examkiosk/.restricted_bashrc"]
    },
    "terminal.integrated.profiles.linux": {
        "RestrictedBash": {
            "path": "/bin/bash",
            "args": ["--noprofile", "--restricted", "--rcfile", "/home/examkiosk/.restricted_bashrc"]
        },
        "bash": null,
        "sh": null,
        "tmux": null,
        "zsh": null
    }
}
EOF
sudo mv /tmp/vscode-settings.json /home/examkiosk/.config/Code/User/settings.json

# 2. Write keybindings.json to disable folder/workspace commands
cat << 'EOF' > /tmp/vscode-keybindings.json
[
    { "key": "ctrl+k ctrl+o", "command": "-workbench.action.files.openFolder" },
    { "key": "ctrl+o", "command": "-workbench.action.files.openFileFolder" },
    { "key": "ctrl+o", "command": "-workbench.action.files.openFile" },
    { "key": "ctrl+shift+p", "command": "-workbench.action.showCommands" },
    { "key": "f1", "command": "-workbench.action.showCommands" }
]
EOF
sudo mv /tmp/vscode-keybindings.json /home/examkiosk/.config/Code/User/keybindings.json


echo ">>> [8] Writing exam session launch script..."
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
  --whitelist=/home/examkiosk/.restricted_bashrc \
  --whitelist=/home/examkiosk/restricted_bin \
  --whitelist=/run/jmx \
  --ignore=nogroups \
  code --kiosk --wait /home/examkiosk/exam_workspace

# When VS Code is closed, kill Openbox and log out
kill $OPENBOX_PID
killall openbox 2>/dev/null || true
EOF

sudo mv "$TMP_SCRIPT" "$DEST"
sudo chmod +x /usr/local/bin/exam-session.sh

echo ">>> [9] Registering exam session with display manager and installing Openbox config..."
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
sudo cp rc.xml /home/examkiosk/.config/openbox/

sudo chown -R examkiosk:examkiosk /home/examkiosk/.config/openbox

echo ">>> [10] Setting up restricted terminal..."
sudo mkdir -p /home/examkiosk/restricted_bin

# Symlink ONLY the allowed commands
# You can add or remove commands from this array as needed
ALLOWED_COMMANDS=("ls" "clear" "java" "javac" "python3" "gcc" "g++")

for cmd in "${ALLOWED_COMMANDS[@]}"; do
    CMD_PATH=$(which $cmd 2>/dev/null)
    if [ -n "$CMD_PATH" ]; then
        sudo ln -sf "$CMD_PATH" "/home/examkiosk/restricted_bin/$cmd"
    fi
done

# Create the restricted bashrc initialization file
cat << 'EOF' > /tmp/.restricted_bashrc
# Set a clean, standard terminal prompt
export PS1='examkiosk@kiosk:\W\$ '

# Restrict the PATH to ONLY our cherry-picked directory
export PATH="/home/examkiosk/restricted_bin"
readonly PATH
EOF

sudo mv /tmp/.restricted_bashrc /home/examkiosk/.restricted_bashrc
sudo chown root:root /home/examkiosk/.restricted_bashrc
sudo chmod 644 /home/examkiosk/.restricted_bashrc
sudo chown -R root:root /home/examkiosk/restricted_bin

# OS level lockdown
# Force the operating system to default this user to restricted bash
sudo usermod -s /bin/rbash examkiosk

echo ">>> [11] Locking down permissions..."
# Run VS Code once (headless) to ensure extension file structure is initialised
sudo -u examkiosk code --list-extensions

# Lock down config files - read-only for examkiosk, owned by root
sudo chown root:root /home/examkiosk/.config/Code/User/settings.json
sudo chmod 644 /home/examkiosk/.config/Code/User/settings.json

sudo chown root:root /home/examkiosk/.config/Code/User/keybindings.json
sudo chmod 644 /home/examkiosk/.config/Code/User/keybindings.json

sudo chown -R root:root /home/examkiosk/.vscode/extensions
sudo chmod 755 /home/examkiosk/.vscode/extensions

# Disabled for testing stage. Enable before final setup
# echo ">>> [Extra] Deleting all other desktop environments"
# sudo find /usr/share/xsessions/ -name "*.desktop" ! -name "exam.desktop" -delete

echo ">>> [12] Configuring launch script for autologin"
# Ensure the desktop file has perfect permissions (sometimes moving from /tmp restricts this)
sudo chmod 644 /usr/share/xsessions/exam.desktop

# Create the .xsessionrc hijack for the examkiosk user
cat << 'EOF' > /tmp/.xsessionrc
# This forcefully hijacks any session SDDM tries to load and routes it to the kiosk
exec /usr/local/bin/exam-session.sh
EOF

# Move it and set the correct permissions
sudo mv /tmp/.xsessionrc /home/examkiosk/.xsessionrc
sudo chown examkiosk:examkiosk /home/examkiosk/.xsessionrc
sudo chmod 644 /home/examkiosk/.xsessionrc

echo ">>> [13] Setting up JMX daemon config files"
sudo mkdir -p /etc/jmxd 

echo ">>> [14] Creating autologin configuration for examkiosk user..."

# Wipe out any default Lubuntu autologin configs that might conflict
sudo rm -f /etc/sddm.conf
sudo rm -f /etc/sddm.conf.d/*.conf
sudo mkdir -p /etc/sddm.conf.d

# Write our definitive config WITH the Theme block restored
sudo tee /etc/sddm.conf.d/10-exam-autologin.conf > /dev/null <<EOF
[Autologin]
User=examkiosk
Session=exam
Relogin=false

[General]
DefaultSession=exam

[Theme]
Current=lubuntu
EOF

# Force AccountsService to recognize the session
sudo mkdir -p /var/lib/AccountsService/users/
cat << 'EOF' | sudo tee /var/lib/AccountsService/users/examkiosk > /dev/null
[User]
Session=exam
XSession=exam
SystemAccount=false
EOF

echo ">>> [15] Installing login background..."
install_plymouth_branding
install_login_background

echo ">>> Exam kiosk setup complete."
