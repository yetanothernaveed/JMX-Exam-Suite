# JMX Onsite Exam Suite

JMX is a comprehensive suite of tools designed to facilitate the creation, management, and evaluation of onsite coding exams at Brac University. It provides a structured framework for organizing exam questions, collecting student responses, and recording results, all in real-time.

JMX features a command line interface that allows exam takers to retrieve questions, submit answers and view their results seamlessly from within a highly secure sandbox environment. The suite also includes a server component that manages the exam flow, ensuring that all interactions are logged and processed efficiently.

JMX has four main components, arranged in three directories:

- **Remote PC Setup**: Uses Lubuntu/Firejail/Openbox and a number of other configurations to launch a secure environment for the exam takers.
- **JMX CLI**: A highly constraint CLI tool that allows exam takers to retrieve questions, submit answers and view their results seamlessly from within a highly secure sandbox environment.
- **JMX Daemon (jmxd)**: A system daemon that runs on the remote PCs, and manages the interactions between the exam takers and the server as the exam takers are trapped inside a sandbox that prevent any and all external communications. JMX creates and listens on an ephemeral unix socket (/run/jmx/jmx.sock). It ensures that all interactions are logged and processed.
- **JMX Server**: This is the heart of the operations. Students get questions, and submit answers to this server. The server executes student code via the Piston code execution environment and returns results back to the remote PCs. Within the server, a MySQL database logs student scores which is then uploaded to Google sheets once the exam ends.

## Installing the remote CLI and daemon

On Ubuntu-based exam PCs, install from the signed public APT repository:

```bash
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://yetanothernaveed.github.io/JMX-APT/KEY.gpg \
  | sudo gpg --dearmor --yes -o /etc/apt/keyrings/jmx.gpg
echo "deb [signed-by=/etc/apt/keyrings/jmx.gpg] https://yetanothernaveed.github.io/JMX-APT stable main" \
  | sudo tee /etc/apt/sources.list.d/jmx.list
sudo apt update
sudo apt install jmxremote
```

Kiosk machines should also install the provisioning/update package:

```bash
sudo apt install jmxsetup
sudo jmx-setup status
sudo jmx-setup config show
```

`jmxsetup` installs the daily 17:05 update timer (skipped during an exam) and
the `jmx-setup` CLI for validated, backed-up edits to
`/etc/jmxd/jmxd.conf`. Update with `sudo apt update && sudo apt upgrade`.
Release and repository maintenance details are in
[`docs/RELEASING.md`](docs/RELEASING.md). The complete Cubic ISO build procedure
is in [`docs/cubic_iso_generation.md`](docs/cubic_iso_generation.md).

Question authors can make selected delivered files editable on the kiosk with a
`writable_` filename prefix; see
[`docs/writable_question_files.md`](docs/writable_question_files.md).

Each directory contains a separate README.md file that provides detailed instructions on how to set up and use the respective components. Please refer to those files for more information on each component.

Developed by YetAnotherNaveed (github.com/YetAnotherNaveed) and the CSE221L (Algorithms Lab) team at Brac University.
