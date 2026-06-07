"""
import_skill.py — add an Agent Skill to this project.

Skills are just folders with a SKILL.md. To use community/Anthropic skills:

  # 1) grab the public library (one time)
  git clone --depth 1 https://github.com/anthropics/skills /tmp/anthropic-skills

  # 2) import the ones you want
  python scripts/import_skill.py /tmp/anthropic-skills/document-skills/pdf
  python scripts/import_skill.py /tmp/anthropic-skills/document-skills/docx

Or import any local skill folder. Each must contain a SKILL.md. They're copied
into ./skills/ and picked up automatically (restart the server).
"""
import os
import sys
import shutil

_SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "skills")


def main(src: str):
    src = os.path.abspath(src)
    if not os.path.isfile(os.path.join(src, "SKILL.md")):
        print(f"ERROR: {src} has no SKILL.md — not a skill folder.")
        return 1
    name = os.path.basename(src.rstrip(os.sep))
    dst = os.path.join(_SKILLS_DIR, name)
    if os.path.exists(dst):
        print(f"'{name}' already exists in skills/ — overwriting.")
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    print(f"Imported skill '{name}' -> skills/{name}. Restart the server to load it.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/import_skill.py <path-to-skill-folder>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
