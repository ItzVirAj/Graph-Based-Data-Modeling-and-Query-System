# My Workflow

I broke the project into stages instead of trying to tackle everything at once, dataset analysis, scaffolding, backend, APIs, LLM integration, frontend, chat UX, testing, auditing, and cleanup. Each stage had to hold up before I moved on.

# How I Ran It

Prompts were task-specific: build the data loader, set up the FastAPI server, wire the query interface, run the final audit. I looked at the actual dataset and PDF before prompting code design, the schema was understood first. During audits, I focused on validation — routes, dependencies, models, data flow. When something broke, I worked from logs and terminal output.

# Patterns That Worked

The flow was: analyze - scaffold - backend - APIs - LLM - frontend - UX - testing - audit - fix. I defined outputs upfront — JSON schemas, API shapes, UI components — so there was less drift. I tested and audited repeatedly. When bugs came up, I brought logs and screenshots to the codex chat, which made fixes faster and less speculative.

# Tools I Used

I used ArenaAI.com - Claude Opus 4.6 thinking for drafting prompts & used GPT Codex (VS Code Extension) to use these prompts on and build the whole App.

# Debugging

.env problems and dependency errors I traced through terminal and Docker logs, checking whether env variables were actually loading, whether packages installed cleanly, and whether the backend was starting the way it should. 

Frontend issues went through browser DevTools: console logs, state inspection, figuring out why 
certain graph elements weren't rendering or showing up at all. 

For Git conflicts I worked through in the terminal during rebase and push, reading the error output carefully to untangle commit history rather than forcing anything through.

# How I Approached It

I treated this like owning the system — breaking it down, validating each piece, debugging with real data, and auditing until it was solid. Not submission-ready in a vague sense. Actually ready.