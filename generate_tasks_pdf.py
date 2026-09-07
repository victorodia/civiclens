import os
from markdown_pdf import Section, MarkdownPdf

task_file = r"C:\Users\Ontop\.gemini\antigravity\brain\d3b27473-4c47-4aaf-98c8-2528279cc4fd\task.md"

with open(task_file, "r", encoding="utf-8") as f:
    text = f.read()

pdf = MarkdownPdf()
pdf.meta["title"] = "Civic Lens Application Task List"
pdf.add_section(Section(text, toc=False))

target_file = r"C:\Users\Ontop\Desktop\Python_Projects\CivicLens\Civic_Lens_Tasks.pdf"
pdf.save(target_file)
print("Comprehensive Task list saved as PDF successfully to CivicLens folder.")
