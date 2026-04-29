package main

import (
	"fmt"
	"os"
	"path/filepath"
)

func main() {
	if (len(os.Args) < 2) {
		fmt.Println("Usage: jmx [option] [<filename>]")
		return
	}
	option := os.Args[1]
	switch option {
	case "start":
		fmt.Println("Welcome to JMX CLI!")
		fmt.Println("Enter your student ID to get started.")

		// Take user input for student ID
		var student_id string
		fmt.Scan(&student_id)

		// ToDo: Establish connection with server.
		var exam_found bool = true // ToDo: Send query to server. 
		if !exam_found {
			fmt.Printf("Currently, there are no ongoing exams for student with ID %s. Please check back later.\n", student_id)
			return
		}

		var exam_id string = "CSE221" // ToDo: Get exam id from server
		fmt.Println()
		fmt.Println("################################################")
		fmt.Println("Hi!")
		fmt.Printf("You are now commencing your exam with ID %s.\n", exam_id)
		fmt.Println("On behalf of the JMX dev team, all the best!")
		fmt.Println("################################################")
		fmt.Println()

	case "submit":
		if (len(os.Args) < 3) {
			fmt.Println("Usage: jmx submit <filename>")
			return
		}
		
		filename := os.Args[2]

		absolutePath, err := filepath.Abs(filename)
		if err != nil {
			fmt.Println("Error resolving file path:", err)
			return
		}

		fmt.Println("Full file path:", absolutePath)
	}

}