# JMX Onsite Exam Suite

JMX is a comprehensive suite of tools designed to facilitate the creation, management, and evaluation of onsite coding exams at Brac University. It provides a structured framework for organizing exam questions, collecting student responses, and recording results all in real-time.

JMX features a command line interface that allows exam takers to retrieve questions, submit answers and view their results seamlessly from within a highly secure sandbox environment. The suite also includes a server component that manages the exam flow, ensuring that all interactions are logged and processed efficiently.

JMX has four main components arranged in three directories:
    - **Remote PC Setup**: Uses a Lubuntu with Firejail and a number of other configurations to launch a secure environment for the exam takers.
    - **JMX CLI**: A highly constraint CLI tool that allows exam takers to retrieve questions, submit answers and view their results seamlessly from within a highly secure sandbox environment.
    - **JMX Daemon (jmxd)**: A system daemon that runs on the remote PCs, and manages the interactions between the exam takers and the server as the exam takers are trapped inside a sandbox that prevent any and all external communications. JMX creates and listens on an ephemeral unix socket (/run/jmx/jmx.sock). It ensures that all interactions are logged and processed efficiently.
    - **JMX Server**: This is the heart of the operations. Student get questions, and submit answers to this server. The server executes student code via Piston code execution environment and returns results back to the remote PCs. Within the server, a MySQL database logs student scores which is then uploaded to Google sheets once the exam ends. 

Each directory contains a separate README.md file that provides detailed instructions on how to set up and use the respective components. Please refer to those files for more information on each component.



Developed by YetAnotherNaveed (github.com/YetAnotherNaveed) and the CSE221L (Algorithms Lab) team at Brac University.
