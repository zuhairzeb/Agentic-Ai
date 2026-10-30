# Final Year Project: RepoGuard

## Current project direction
**Title:** RepoGuard: An MCP Based AI Agent for GitHub Security Reports in English and Roman Urdu

This is the current saved topic. The user previously considered UniGuide offline RAG, but RepoGuard is the current direction in the available context.

## Student context and constraints
- BS Artificial Intelligence undergraduate.
- Proposal is for supervisor review first; formal proposal submission was expected in the 8th semester in prior notes. Confirm the current academic schedule.
- Supervisor named in prior context: Dr. Naveed Abbas.
- The user wants a manageable undergraduate project that uses familiar skills and does not depend on advanced ML, DL, or CNN knowledge.
- No paid APIs.
- A normal laptop should be enough for the planned scope.
- Offline operation is **out of scope**. Do not add offline mode as a requirement.
- The proposal should sound like a student wrote it: simple, clear, realistic, and not over-polished.
- The user requested no timeline section in the proposal.
- Do not claim results or successful detection before implementation and evaluation.

## Problem and aim
RepoGuard is intended to help a developer understand security findings from GitHub repositories by bringing together outputs from selected existing scanning tools, summarizing the findings, highlighting or tagging issues, and generating a report in English or Roman Urdu.

The agent should explain tool findings; it should not claim to discover every possible vulnerability or replace a security expert.

## Scope decisions
- Use MCP (Model Context Protocol) to connect the agent to suitable tools.
- Choose feasible security data sources and scanning tools.
- Use multiple scanners/tools if practical.
- Focus on security findings and their explanations.
- Evaluate retrieval quality, explanation accuracy, and English/Roman Urdu output quality.
- Avoid claiming complete vulnerability detection.
- Do not make the system “scan every possible issue in all of GitHub”.
- Do not make offline use a core requirement.

## Possible high-level workflow
1. User provides a public repository URL or an authorized repository connection.
2. Agent checks repository information and runs or retrieves findings from supported tools.
3. Agent normalizes findings into a common structure.
4. Agent groups findings by severity or category when the source provides that information.
5. Agent explains each finding in plain English or Roman Urdu.
6. Agent creates a report with finding, source tool, severity as reported by the tool, evidence/location, risk explanation, and suggested next step.
7. Agent clearly marks uncertain findings and avoids presenting suggestions as confirmed fixes.
8. Evaluation compares the report with source tool output and human-reviewed examples.

## Example report fields
- Repository name and URL
- Scan date
- Tools used and versions, if available
- Finding title
- Severity reported by the source tool
- File path and line number, if supplied
- Source tool and original finding ID
- Plain-language explanation
- English explanation
- Roman Urdu explanation
- Suggested next step
- Confidence or uncertainty note
- Link to the original source finding

## Evaluation ideas
Define the test plan before implementation:
- **Finding coverage:** Did the agent include the findings that the connected tools reported?
- **Faithfulness:** Does the explanation match the source finding?
- **Retrieval accuracy:** Does the agent retrieve the correct repository and finding details?
- **Language quality:** Are English and Roman Urdu explanations clear and consistent?
- **Human review:** Ask a reviewer to score correctness and clarity using a simple rubric.
- **Failure analysis:** Record missing findings, incorrect severity, unsupported advice, and translation errors.

Do not call these measures “accuracy results” until the test has been run and scores calculated.

## Safety and limits
- Only scan repositories the user owns or is authorized to test.
- Use read-only access unless a separate action is explicitly approved.
- Do not automatically modify code, open pull requests, or change repository settings without permission.
- Never claim a clean scan proves a repository is secure.
- Scanner output may contain false positives and false negatives.
- Do not expose access tokens, secrets, or private repository content in reports or logs.
- Explain that results depend on the tools and repository content that were available.

## Proposal outline
1. Title
2. Introduction
3. Problem Statement
4. Aim and Objectives
5. Research Questions
6. Related Work
7. Proposed Methodology
8. Evaluation Plan
9. Expected Output
10. Scope and Limitations
11. Ethical and Privacy Considerations
12. References

No timeline section unless the supervisor later requires one.
