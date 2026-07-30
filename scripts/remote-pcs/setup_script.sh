#!/bin/bash
set -e

echo ">>> [0.1/8] Load custom branding..."
# Load helper functions
source branding/branding.sh

echo ">>> [1/8] Installing system dependencies..."
sudo apt update
sudo apt install -y build-essential python3 openjdk-21-jdk openbox firejail sqlite3 libsqlite3-dev

echo ">>> [2/8] Installing VS Code..."
sudo apt-get install -y wget gpg
wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
sudo install -D -o root -g root -m 644 packages.microsoft.gpg /etc/apt/keyrings/packages.microsoft.gpg
sudo sh -c 'echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list'
rm -f packages.microsoft.gpg
sudo apt update && sudo apt install -y code

echo ">>> [3/8] Creating examkiosk user and workspace..."
if ! id examkiosk &>/dev/null; then
    adduser --disabled-password --gecos "" examkiosk
fi

EXAMKIOSK_PASSWORD="2304"
# Set the default password
echo "examkiosk:${EXAMKIOSK_PASSWORD}" | chpasswd

mkdir -p /home/examkiosk/exam_workspace
chown examkiosk:examkiosk /home/examkiosk/exam_workspace
chmod 700 /home/examkiosk/exam_workspace

echo ">>> [3.1/8] Creating new user group jmx and adding user examkiosk to the jmx group"
getent group jmx >/dev/null || groupadd --system jmx
sudo usermod -aG jmx examkiosk

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

echo ">>> [5/8] Writing VS Code settings and keybindings..."

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
    "terminal.integrated.defaultProfile.linux": "RestrictedBash",
    "terminal.integrated.automationProfile.linux": {
        "path": "/bin/bash",
        "args": ["--restricted", "--rcfile", "/home/examkiosk/.restricted_bashrc"]
    },
    "terminal.integrated.profiles.linux": {
        "RestrictedBash": {
            "path": "/bin/bash",
            "args": ["--restricted", "--rcfile", "/home/examkiosk/.restricted_bashrc"]
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
  --whitelist=/run/jmx \
  --ignore=nogroups \
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
sudo cp rc.xml /home/examkiosk/.config/openbox/


echo ">>> [7.5/8] Setting up restricted terminal..."

# 1. Create the whitelist directory for commands
sudo mkdir -p /home/examkiosk/restricted_bin

# 2. Symlink ONLY the allowed commands
# You can add or remove commands from this array as needed
ALLOWED_COMMANDS=("ls" "clear" "java" "javac" "python3" "gcc" "g++")

for cmd in "${ALLOWED_COMMANDS[@]}"; do
    CMD_PATH=$(which $cmd 2>/dev/null)
    if [ -n "$CMD_PATH" ]; then
        sudo ln -sf "$CMD_PATH" "/home/examkiosk/restricted_bin/$cmd"
    fi
done

# 3. Create the restricted bashrc initialization file
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

echo ">>> [7.1/8] Locking down permissions..."
# Run VS Code once (headless) to ensure extension file structure is initialised
sudo -u examkiosk code --list-extensions

# Lock down config files - read-only for examkiosk, owned by root
sudo chown root:root /home/examkiosk/.config/Code/User/settings.json
sudo chmod 644 /home/examkiosk/.config/Code/User/settings.json

sudo chown root:root /home/examkiosk/.config/Code/User/keybindings.json
sudo chmod 644 /home/examkiosk/.config/Code/User/keybindings.json

sudo chown -R root:root /home/examkiosk/.vscode/extensions
sudo chmod 755 /home/examkiosk/.vscode/extensions

# FIX: Ensure examkiosk owns its extensions so Java can unpack its server and write logs
# sudo chown -R examkiosk:examkiosk /home/examkiosk/.vscode
# sudo chmod -R 755 /home/examkiosk/.vscode

# Disabled for testing stage. Enable before final setup
# echo ">>> [Extra] Deleting all other desktop environments"
# sudo find /usr/share/xsessions/ -name "*.desktop" ! -name "exam.desktop" -delete

echo ">>> [7.2/8] Setting up JMX daemon config files"
sudo mkdir -p /etc/jmxd 

echo ">>> [7.3/8] Creating autologin configuration for examkiosk user..."
mkdir -p /etc/sddm.conf.d
cat > /etc/sddm.conf.d/autologin.conf <<EOF
[Autologin]
User=examkiosk
Session=exam
Relogin=false

[General]
DefaultSession=exam.desktop

[Users]
RememberLastUser=false
RememberLastSession=false
EOF

echo ">>> [7.4/8] Installing login background..."
install_plymouth_branding
install_login_background

echo ">>> Exam kiosk setup complete."
