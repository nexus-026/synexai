import re
from typing import Dict, Any


class CodeEngine:
    """
    Independent code generation engine.
    No external AI APIs — uses templates, syntax analysis, and pattern matching.
    """

    LANGUAGES = {
        "python": {"ext": "py", "comment": "#"},
        "javascript": {"ext": "js", "comment": "//"},
        "html": {"ext": "html", "comment": "<!-- -->"},
        "css": {"ext": "css", "comment": "/* */"},
        "php": {"ext": "php", "comment": "//"},
        "sql": {"ext": "sql", "comment": "--"},
        "java": {"ext": "java", "comment": "//"},
        "cpp": {"ext": "cpp", "comment": "//"},
        "c#": {"ext": "cs", "comment": "//"},
        "typescript": {"ext": "ts", "comment": "//"},
        "go": {"ext": "go", "comment": "//"},
        "rust": {"ext": "rs", "comment": "//"},
        "bash": {"ext": "sh", "comment": "#"},
    }

    async def handle(self, message: str) -> Dict[str, Any]:
        lang = self._detect_language(message)
        task = self._detect_task(message)

        if task == "generate":
            code = self._generate_code(lang, message)
        elif task == "explain":
            code = self._extract_code(message) or "# No code provided"
            explanation = self._explain_code(code, lang)
            return {
                "success": True,
                "type": "code",
                "response": f"**Code Explanation ({lang}):**\n\n{explanation}",
                "sources": [],
            }
        elif task == "debug":
            code = self._extract_code(message) or "# No code provided"
            fixed = self._debug_code(code, lang)
            return {
                "success": True,
                "type": "code",
                "response": f"**Debugged Code ({lang}):**\n\n```{lang}\n{fixed}\n```",
                "sources": [],
            }
        elif task == "convert":
            target = self._detect_target_lang(message) or "python"
            code = self._extract_code(message) or "# No code provided"
            converted = self._convert_code(code, lang, target)
            return {
                "success": True,
                "type": "code",
                "response": f"**Converted from {lang} to {target}:**\n\n```{target}\n{converted}\n```",
                "sources": [],
            }
        else:
            code = self._generate_code(lang, message)

        quality = self._score_quality(code, lang)
        response = f"**Generated {lang.capitalize()} Code** (Quality: {quality}/10)\n\n```{lang}\n{code}\n```\n\n"
        response += self._get_tips(lang, code)

        return {
            "success": True,
            "type": "code",
            "response": response,
            "sources": [],
        }

    def _detect_language(self, msg: str) -> str:
        lower = msg.lower()
        for lang in self.LANGUAGES:
            if lang in lower:
                return lang
        if any(k in lower for k in ["web page", "website", "form", "div", "span"]):
            return "html"
        if any(k in lower for k in ["query", "database", "table", "select", "insert"]):
            return "sql"
        return "python"

    def _detect_task(self, msg: str) -> str:
        lower = msg.lower()
        if any(k in lower for k in ["explain", "what does", "how does", "describe"]):
            return "explain"
        if any(k in lower for k in ["debug", "fix", "error", "bug", "not working"]):
            return "debug"
        if any(k in lower for k in ["convert", "translate to", "rewrite in"]):
            return "convert"
        return "generate"

    def _detect_target_lang(self, msg: str) -> str:
        lower = msg.lower()
        for lang in self.LANGUAGES:
            if f"to {lang}" in lower or f"in {lang}" in lower:
                return lang
        return "python"

    def _extract_code(self, msg: str) -> str:
        # Extract code blocks
        m = re.search(r'```(\w+)?\n(.*?)```', msg, re.S)
        if m:
            return m.group(2).strip()
        # Extract indented or plain code
        lines = msg.split("\n")
        code_lines = []
        in_code = False
        for line in lines:
            if line.strip().startswith(("def ", "class ", "function ", "import ", "const ", "let ", "var ", "#include", "public ", "private ")):
                in_code = True
            if in_code:
                code_lines.append(line)
        return "\n".join(code_lines)

    def _generate_code(self, lang: str, prompt: str) -> str:
        generators = {
            "python": self._gen_python,
            "javascript": self._gen_javascript,
            "html": self._gen_html,
            "css": self._gen_css,
            "php": self._gen_php,
            "sql": self._gen_sql,
            "java": self._gen_java,
            "cpp": self._gen_cpp,
        }
        gen = generators.get(lang, self._gen_python)
        return gen(prompt)

    def _gen_python(self, prompt: str) -> str:
        if "sort" in prompt.lower():
            return '''def quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + middle + quicksort(right)

# Example usage
if __name__ == "__main__":
    data = [3, 6, 8, 10, 1, 2, 1]
    print(quicksort(data))'''
        if "api" in prompt.lower() or "fastapi" in prompt.lower():
            return '''from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: str = None):
    return {"item_id": item_id, "q": q}'''
        if "scrape" in prompt.lower() or "crawl" in prompt.lower():
            return '''import requests
from bs4 import BeautifulSoup

def fetch_title(url: str) -> str:
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        return soup.title.string.strip() if soup.title else "No title"
    except Exception as e:
        return str(e)

if __name__ == "__main__":
    print(fetch_title("https://example.com"))'''
        return '''def main():
    """Main function."""
    print("Hello, World!")

if __name__ == "__main__":
    main()'''

    def _gen_javascript(self, prompt: str) -> str:
        return '''function greet(name) {
    return `Hello, ${name}!`;
}

// Example
console.log(greet("World"));

// Async example
async function fetchData(url) {
    const response = await fetch(url);
    return response.json();
}'''

    def _gen_html(self, prompt: str) -> str:
        return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My Page</title>
    <style>
        body { font-family: sans-serif; margin: 2rem; }
        .card { border: 1px solid #ddd; padding: 1rem; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Welcome</h1>
        <p>This is a generated HTML page.</p>
    </div>
</body>
</html>'''

    def _gen_css(self, prompt: str) -> str:
        return '''/* Modern reset */
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'Segoe UI', sans-serif;
    background: #f8fafc;
    color: #1e293b;
    line-height: 1.6;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem;
}

.btn {
    display: inline-block;
    padding: 0.75rem 1.5rem;
    background: #3b82f6;
    color: white;
    border-radius: 6px;
    text-decoration: none;
    transition: background 0.2s;
}

.btn:hover { background: #2563eb; }'''

    def _gen_php(self, prompt: str) -> str:
        return '''<?php
function sanitize(string $input): string {
    return htmlspecialchars(trim($input), ENT_QUOTES, 'UTF-8');
}

$message = "Hello from NXS AI PHP backend!";
echo sanitize($message);
?>'''

    def _gen_sql(self, prompt: str) -> str:
        return '''-- Create users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert sample
INSERT INTO users (username, email, hashed_password)
VALUES ('admin', 'admin@nxs.ai', 'hashed_secret');

-- Query
SELECT * FROM users WHERE is_active = TRUE ORDER BY created_at DESC;'''

    def _gen_java(self, prompt: str) -> str:
        return '''public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, NXS AI!");
    }

    public static int add(int a, int b) {
        return a + b;
    }
}'''

    def _gen_cpp(self, prompt: str) -> str:
        return '''#include <iostream>
#include <vector>

int main() {
    std::vector<int> nums = {1, 2, 3, 4, 5};
    for (int n : nums) {
        std::cout << n << " ";
    }
    return 0;
}'''

    def _explain_code(self, code: str, lang: str) -> str:
        lines = code.strip().split("\n")
        explanation = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("def ", "function ", "public ", "class ")):
                explanation.append(f"**Line {i}:** Defines a function/class: `{stripped[:60]}...`")
            elif stripped.startswith(("import ", "from ", "#include", "using ")):
                explanation.append(f"**Line {i}:** Imports dependencies.")
            elif stripped.startswith(("return ", "echo ", "print", "console.log")):
                explanation.append(f"**Line {i}:** Returns/outputs a value.")
            elif "if " in stripped or "for " in stripped or "while " in stripped:
                explanation.append(f"**Line {i}:** Control flow statement.")
            else:
                explanation.append(f"**Line {i}:** Execution statement.")
        return "\n".join(explanation) or "This is a simple script with no complex logic detected."

    def _debug_code(self, code: str, lang: str) -> str:
        # Simple static fixes
        fixed = code
        if lang == "python":
            fixed = re.sub(r'print\s+([^(\n]+)', r'print(\1)', fixed)  # Python 2 print
            fixed = fixed.replace("except:", "except Exception as e:")
        if lang == "javascript":
            fixed = re.sub(r'var\s+', 'const ', fixed)
        return fixed

    def _convert_code(self, code: str, from_lang: str, to_lang: str) -> str:
        # Naive conversion for demo — real system would use AST parsers
        if from_lang == "python" and to_lang == "javascript":
            return code.replace("def ", "function ").replace(":", " {").replace("print(", "console.log(")
        if from_lang == "javascript" and to_lang == "python":
            return code.replace("function ", "def ").replace("{", ":").replace("console.log(", "print(")
        return f"// Conversion from {from_lang} to {to_lang} requires manual review.\n" + code

    def _score_quality(self, code: str, lang: str) -> int:
        score = 5
        if len(code) > 200:
            score += 1
        if "error" in code.lower() or "fixme" in code.lower():
            score -= 2
        if lang == "python" and "def " in code and '"""' in code:
            score += 2  # Has docstrings
        if "try:" in code and "except" in code:
            score += 1  # Error handling
        return max(1, min(10, score))

    def _get_tips(self, lang: str, code: str) -> str:
        tips = {
            "python": "💡 Tip: Use type hints and `pydantic` for API validation.",
            "javascript": "💡 Tip: Prefer `const`/`let` over `var`. Use async/await for I/O.",
            "html": "💡 Tip: Always include `lang` attribute and meta viewport.",
            "css": "💡 Tip: Use CSS variables for theming and `rem` units for accessibility.",
            "php": "💡 Tip: Use prepared statements to prevent SQL injection.",
            "sql": "💡 Tip: Add indexes on frequently queried columns.",
            "java": "💡 Tip: Use `Optional` and streams for null-safety.",
            "cpp": "💡 Tip: Prefer smart pointers (`std::unique_ptr`) over raw pointers.",
        }
        return tips.get(lang, "💡 Tip: Write tests for your code.")
