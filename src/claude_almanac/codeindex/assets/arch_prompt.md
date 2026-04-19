You are summarizing one module of a codebase for retrieval-based search.

Produce a concise summary in 3-5 sentences covering:
- What the module does (its purpose)
- Its public surface (for code modules, name key exports/functions/classes; for config modules, name key resources/values)
- Its main dependencies (other modules, external services, notable libraries)

Rules:
- Be factual. Cite specific names as they appear in the code.
- If the module's purpose is unclear from the file set, say so — do NOT invent.
- Do not list every file. Summarize the module, not its contents.
- Output only the summary text. No preamble, no bullet lists, no markdown headers.

Module: {module_name}
Language mix: {language_mix}

Files:
{file_sections}
