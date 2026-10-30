# Research Guide and Reusable Templates

This file teaches the agent how to support research work. It is a workflow, not a claim that research has already been conducted.

## A. Basic research workflow

### 1. Define the problem
Write one clear paragraph:
- What problem exists?
- Who experiences it?
- Why does it matter?
- What is missing from current solutions or knowledge?

Avoid starting with a broad topic such as “AI in education”. Narrow it to a problem that can be studied with the time, skills, and resources available.

### 2. Review existing work
Search for relevant papers, books, official reports, standards, and trusted technical documentation.
For each source, record:
- Full title
- Authors or organization
- Year
- Publisher, journal, or conference
- DOI or stable URL
- Research question or purpose
- Method or tools used
- Dataset or sample, if any
- Main result
- Limitations
- How it relates to the proposed project

Do not invent papers, authors, citations, DOI numbers, or results. If a source cannot be verified, label it “not verified”.

### 3. Find the gap
A research gap is a specific limitation or unanswered question in existing work. It is not enough to say “no one has done this before”.
Possible gap types:
- A tool does not explain findings clearly.
- A method has not been tested in a specific setting.
- Existing systems do not support a target language or user group.
- Studies use different measures, making results hard to compare.
- A practical constraint has not been addressed.
The gap must be supported by the literature review.

### 4. Set objectives and questions
Write one main objective and 2–5 smaller objectives.
Each objective should be observable and possible to complete.
Research questions should directly match the objectives.

### 5. Choose a method
Explain:
- Research design
- Data sources
- Selection rules
- Tools or models
- Steps for collecting data
- Steps for processing or analyzing data
- Evaluation measures
- Ethical, privacy, and safety steps
- Limits of the method

Choose a method based on the question, not because a method sounds advanced.

### 6. Plan evaluation
Before running experiments, define what success means.
Examples:
- Accuracy of extracted information
- Precision, recall, and F1 when valid labels exist
- Human rating of explanation clarity
- Correctness of generated summaries
- Task completion rate
- Response time
- Comparison against a baseline
- Error analysis
Do not report scores until tests have actually been run. State the test set, scoring method, and limitations.

### 7. Write results and discussion
Results should report what the evidence shows.
Discussion should explain:
- What the result may mean
- How it compares with previous work
- Where it failed
- What may explain the errors
- What cannot be concluded

Keep results and guesses separate.

### 8. State limitations
Common limits include small samples, limited time, limited computing power, language coverage, incomplete datasets, tool-specific output, and human-rating bias.
A clear limitation is better than an unsupported claim.

### 9. Cite sources
Use the style required by the university or supervisor. If none is specified, ask before final formatting.
Keep in-text citations and reference-list entries matched.
Never fabricate references.

## B. Research proposal template

# Title
A short title that names the system, problem, or question clearly.

## 1. Introduction
Describe the topic, setting, problem, and why it matters. End by introducing the proposed work.

## 2. Problem Statement
State the exact problem and what current approaches do not fully address.

## 3. Aim
One sentence describing the main purpose.

## 4. Objectives
1. Objective one
2. Objective two
3. Objective three

## 5. Research Questions
1. Question that matches Objective 1
2. Question that matches Objective 2
3. Question that matches Objective 3

## 6. Related Work
Summarize the most relevant verified studies. Compare their approaches, findings, and limits. Explain the gap.

## 7. Proposed Methodology
Describe data sources, tools, process, implementation, and evaluation plan in enough detail that another student could follow it.

## 8. Evaluation Plan
List metrics, test cases, baseline or comparison method, and how results will be judged.

## 9. Expected Output
Describe deliverables that are planned, not results that are already achieved.

## 10. Scope and Limitations
State what is included and excluded.

## 11. Ethical and Privacy Considerations
Explain permissions, data handling, anonymity where relevant, and responsible use.

## 12. References
List only sources that have been checked.

Do not add a timeline section if the user has said the required proposal should not include one.

## C. Research paper structure

1. Title
2. Abstract
3. Keywords
4. Introduction
5. Related Work / Literature Review
6. Methodology
7. Results
8. Discussion
9. Limitations
10. Conclusion and Future Work
11. References
12. Appendices, if needed

### Abstract checklist
Usually 150–250 words, unless the venue says otherwise:
- Context or problem
- Aim
- Method
- Data or evaluation setup
- Main result, only if available
- Main conclusion, only if supported

Do not write final results in an abstract before experiments are complete.

## D. Literature review table template

| ID | Citation | Problem | Method / Tool | Dataset / Sample | Main Finding | Limitation | Relevance |
|---|---|---|---|---|---|---|---|
| 1 | Author, year, title, DOI/URL | | | | | | |

## E. Research summary template

# Research Summary
- **Topic:**
- **Problem:**
- **Why it matters:**
- **Research question:**
- **What prior work says:**
- **Gap:**
- **Proposed method:**
- **Data and tools:**
- **Evaluation plan:**
- **Main findings:** Not available until measured
- **Limitations:**
- **Next steps:**
- **Verified sources:**

## F. CV-style profile template

# Name
**Target role:**  
**Location / Remote preference:**  
**Email / Portfolio / LinkedIn / GitHub:**  

## Professional Summary
Write 3–5 short lines: experience, core skills, strongest evidence, and target direction.

## Core Skills
Group related skills rather than listing every tool without context.

## Experience
For each role:
- Job title and organization
- Dates
- 3–5 bullets beginning with clear action words
- Mention tools and outcomes
- Use numbers only when verified

## Projects
For each project:
- Project name
- Problem it solves
- What was built
- Tools used
- What the user personally contributed
- Link
- Measured outcome, if available

## Education
Degree, institute, dates or expected completion.

## Awards and Volunteering
Include only verified items.

## Quality rules for CV writing
- Never invent results, clients, dates, or percentages.
- Use specific action and outcome language.
- Tailor the CV to the job description.
- Keep it ATS-friendly and easy to scan.
- Do not describe the user as a Data Analyst or Power BI specialist when the target is WordPress development.
- Keep a master CV with all verified details, then create shorter targeted versions.
