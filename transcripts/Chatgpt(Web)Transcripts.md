# ChatGPT - Prompt generation for Claude

## User

write a prompt for claude to generaet a prompt.md , instructions.md file and utiize the least tokens .


---

## ChatGPT

If your goal is **minimum token usage** while still getting Claude to generate high-quality `prompt.md` and `instructions.md` files, give Claude a meta-prompt that focuses on compression, avoiding explanations, and producing only the required files.

# ROLE

Generate two files:

1. `prompt.md`
2. `instructions.md`

# OBJECTIVE

Create production-ready AI project documentation using the FEWEST possible tokens while preserving clarity and completeness.

# RULES

- No introductions.
- No explanations.
- No reasoning.
- No examples unless required.
- No duplicated information between files.
- Prefer bullets over paragraphs.
- Prefer constraints over descriptions.
- Use concise wording.
- Remove filler, marketing language, and verbosity.
- Output ONLY the file contents.

# FILE: prompt.md

Include only:
- Project goal
- Inputs
- Outputs
- Functional requirements
- Non-functional requirements
- Deliverables
- Acceptance criteria

Use compact markdown.

# FILE: instructions.md

Include only:
- System behavior
- Coding standards
- Architecture constraints
- Error handling rules
- Security requirements
- Testing requirements
- Documentation requirements
- Prohibited actions

Use imperative statements.

# OUTPUT FORMAT

```text
=== prompt.md ===
<content>

=== instructions.md ===
<content>
```

Generate the final versions directly.

For even lower token usage, append:

> "Optimize for information density. Every line must justify its existence. Target <500 total tokens across both files unless requirements demand more."


---

## User

even this prompt should take less tokens


---

## ChatGPT

Use this ultra-short version:

```text
Generate:

1. prompt.md
2. instructions.md

Rules:
- Minimal tokens.
- No explanations.
- No examples.
- No filler.
- No duplicated content.
- Markdown only.

prompt.md:
goal, inputs, outputs, requirements, deliverables, acceptance criteria.

instructions.md:
behavior, standards, constraints, security, testing, documentation, prohibitions.

Output:
=== prompt.md ===
<content>

=== instructions.md ===
<content>
```

For maximum compression:

```text
Create prompt.md + instructions.md.

Use minimum tokens.

prompt.md: goal, inputs, outputs, reqs, deliverables, acceptance.
instructions.md: behavior, standards, constraints, security, testing, docs, prohibitions.

No prose. No explanations. No duplication.

Output only file contents.
```

This is about as short as you can get before Claude starts losing structure and quality.


---
