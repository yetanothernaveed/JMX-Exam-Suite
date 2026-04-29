from pathlib import Path
from re import sub
import subprocess

def execute_from_disk(lang: str, filename: str, work_dir: Path, problem_id: str) -> str:
    file_path = work_dir / filename
    try:
        if lang == "python":
            cmd = ["python3", str(file_path)]
        elif lang == "cpp":
            exe_path = work_dir / "out"
            compile_res = subprocess.run(
                ["g++", str(file_path), "-o", str(exe_path)], 
                capture_output=True, 
                text=True
            )

            if compile_res.returncode != 0:
                return f"Compilation Error:\n{compile_res.stderr}"
            cmd = [str(exe_path)]
        elif lang == "java":
            compile_res = subprocess.run(
                ["javac", str(file_path)],
                capture_output=True,
                text=True
            )

            if compile_res.returncode != 0:
                return f"Compilation Error:\n{compile_res.stderr}"
            
            class_name = Path(filename).stem
            cmd = ["java", "-cp", str(work_dir), class_name]
        else:
            return "400 Unsupported language"
        
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return (res.stdout + res.stderr) if (res.stdout + res.stderr) else "[No Output]"
    
    except subprocess.TimeoutExpired:
        return f"Error: Execution timeout (10s)"
    except Exception as e:
        return f"Server Error: {str(e)}"
    
if __name__ == "__main__":
    lang = "java" # input("Enter your prefered language (python or java or cpp): ")
    filename = "A.java" # input("Enter filename: ")
    work_dir = Path("/home/naveed/Work/jmx-server") # Path(input("Enter working directory: "))
    problem_id = "_313" # input("Enter problem ID (_313): ")

    o = execute_from_disk(lang, filename, work_dir, problem_id)
    print(o)