import subprocess
from pathlib import Path


def build_knowledge_base() -> bool:
    """Compile Obsidian notes via Quartz into app/static/kb/."""
    print("Compiling Quartz Knowledge Base...")

    engine_dir = Path(__file__).parent.parent / ".quartz-engine"
    output_dir = Path(__file__).parent.parent / "app" / "static" / "kb"
    output_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["npx", "quartz", "build", "-o", str(output_dir)],
        cwd=str(engine_dir),
    )

    if result.returncode == 0:
        print(f"Knowledge base built successfully → {output_dir}")
        return True
    else:
        print("Error compiling knowledge base.")
        return False


if __name__ == "__main__":
    build_knowledge_base()
