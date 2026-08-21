# Google Stitch UI Brief: Position Description Management System

## Purpose

Design a professional, accessible web application for managing position descriptions (PDs).

The system turns static Word position descriptions into structured, reviewable, searchable data. It helps users:

- upload a Word PD
- validate extracted fields
- store the validated PD in a database
- search for existing roles
- identify similar roles
- use evidence-based recommendations to map roles into a job family framework
- administer supporting reference data such as classifications and framework/mapping imports

This is a human-in-the-loop decision-support tool. It should not look or feel like an automated black box. The app should help users make better, faster, more consistent decisions while keeping human judgement visible.

## Target users

Primary users:

- HR/workforce design staff
- role description / position management staff
- job architecture or job family framework owners
- analysts supporting workforce reporting and governance

Secondary users:

- managers or business representatives reviewing a role
- administrators maintaining reference data
- future governance/audit users

## Design tone

The design should feel:

- professional
- clear
- trustworthy
- government/public-sector appropriate
- calm rather than flashy
- modern but not gimmicky
- accessible and readable for heavy text review

Avoid:

- playful SaaS styling
- excessive cards everywhere
- dense technical dashboards
- overcomplicated analytics visuals
- hiding evidence behind opaque scores

The app handles long text, structured fields, and decision evidence, so information hierarchy is critical.

## Core product idea

The product is not just an extractor.

It is a workflow for converting Word PDs into a governed structured data asset that can support:

- PD quality assurance
- role search
- similar-role discovery
- job family mapping
- classification/grade analysis
- workforce reporting
- future PD maintenance

## Main navigation

Suggested top-level navigation:

1. Dashboard
2. Upload PD
3. Validation Queue
4. Role Search
5. Mapping Assistant
6. Admin

Admin could contain:

- Classification Admin
- Framework and Mapping Import
- Future: Users and Permissions
- Future: Audit/Activity Log

## Key workflows

### Workflow 1: Upload and validate a PD

User story:

> As a user, I want to upload a Word position description, review the extracted fields, correct anything needed, and validate the PD so it becomes part of the structured database.

Steps:

1. User uploads a `.docx` file.
2. System extracts structured fields.
3. User is taken to a validation review screen.
4. User reviews each section.
5. User edits extracted data where needed.
6. User validates the PD.
7. PD is stored as validated in the database.
8. System prepares the PD for search and mapping assistant use.

Important UI needs:

- clear extraction status
- clear validation status
- ability to save draft
- ability to validate entire PD
- ability to see sections that may need review
- no field should be mandatory, because some PDs are valid exceptions
- source Word document should remain accessible

### Workflow 2: Validation queue

User story:

> As a user, I want to see all uploaded PDs that are not yet validated, so I can work through them later.

Screen should show:

- PD ID
- role title
- classification/grade
- upload date
- extraction status
- validation status
- possible review flags
- action: open validation review

Useful filters:

- not validated
- needs review
- validated
- classification/grade
- uploaded date

### Workflow 3: Find an existing PD

User story:

> As a user, I want to quickly find a known role by PD ID or title.

Search should support:

- PD ID, e.g. `10681` or `10681-01`
- role title
- partial title
- classification/grade filter
- mapped/unmapped filter

Results should show:

- PD ID
- role title
- classification/grade
- mapped job family/sub-family/specialisation
- validation status
- action: open role detail

### Workflow 4: Free-text semantic role search

User story:

> As a user, I want to describe a role in plain language and find similar existing roles.

Example query:

> "creates reports and does data analysis and communicates insights to stakeholders"

Results should show:

- similarity score
- PD ID
- role title
- classification/grade
- job family mapping
- whether the mapping is validated
- short evidence snippet if possible

Important design point:

Semantic search is useful but imperfect. The UI should avoid implying the top result is always “correct”. It should invite human judgement.

Potential explanatory copy:

> These results are based on semantic similarity, not keyword matching alone. Review the role details and mapped job family before making a decision.

### Workflow 5: Mapping Assistant

User story:

> As a user, I want help mapping an unmapped or uncertain PD into the job family framework by reviewing similar mapped roles and framework suggestions.

The assistant should:

- accept a PD ID or selected PD
- show top recommended job families first
- allow user to click into a job family to view likely sub-families and specialisations
- show similar mapped roles as evidence
- show whether evidence roles have validated mappings
- show classification/grade context
- allow filtering by job family and classification cohort
- support human selection of the final mapping

Important principle:

Do not overwhelm the user with the full framework all at once. Start with the top 3 likely job families, then let the user drill down.

Recommended structure:

1. PD summary panel
   - role title
   - PD ID
   - classification/grade
   - current mapping status

2. Recommended job families
   - top 3 ranked options
   - plain-language explanation of why each appears
   - score/evidence shown in a restrained way

3. Drill-down panel
   - when a job family is selected, show likely sub-families and specialisations
   - include framework definitions if available
   - include exclusions/warnings if available, but do not treat exclusions as positive evidence

4. Similar mapped roles
   - evidence table
   - role title
   - PD ID
   - similarity
   - classification/grade
   - mapping
   - validated mapping indicator

5. Final mapping action
   - select mapping
   - mark as validated or draft
   - save to database

Important UI caution:

The framework is multi-layered. The user may not know the framework well. The design should guide them progressively rather than making them compare long lists.

### Workflow 6: Classification Admin

User story:

> As an admin, I want to clean up and manage classification/grade labels so they can be grouped, abbreviated, ordered, and used consistently in search and mapping.

Fields:

- raw classification label
- corrected display label
- abbreviation, e.g. `TWL8`, `TWL9`, `TM1`
- cohort/group, e.g. `TWL8-TM1`
- numeric order
- active/inactive flag if useful

Needs:

- editable table
- save changes
- export CSV
- export JSON
- changes flow into search, filters, and mapping assistant

### Workflow 7: Framework and Mapping Workbook Import

User story:

> As an admin, I want to upload an updated workbook containing the job family framework and role mappings, so the system uses the latest reference data.

Workbook contains:

- job family framework sheet
- mapping input sheet

Important known sheet names:

- `job_family_power_query`
- `job_mapping_input`

The system should:

- identify the correct sheets
- import framework rows
- import mapping rows
- match PD mappings using the 5-digit PD ID prefix
- validate mapping codes against the framework
- report invalid codes
- report mapping rows that do not link to PDs
- show how many distinct PD IDs are mapped
- show how many distinct PD IDs have validated mappings
- regenerate framework embeddings if framework definitions change

## Important data concepts

### Position Description

Fields include:

- PD ID, e.g. `10681-01`
- 5-digit base PD ID, e.g. `10681`
- role title
- classification/grade
- primary purpose
- key accountabilities
- key challenges
- key relationships
- essential requirements
- capabilities
- source filename
- extraction status
- validation status
- mapping status

### Job family framework

The framework is hierarchical:

- Job Family
- Sub-family
- Specialisation

Framework rows can include:

- code
- name
- level
- parent code
- main definition
- supplementary definition 1
- supplementary definition 2
- exclusions

Important design point:

When showing a sub-family or specialisation, also show the parent levels so users understand where it sits.

### Role mapping

A PD may map to:

- job family
- sub-family
- specialisation

Mapping may be:

- unmapped
- mapped but not validated
- mapped and validated

The mapping assistant should prefer validated mappings as stronger evidence, while still showing unvalidated evidence carefully.

### Classification/grade

Classifications vary across agreements and historical labels.

The system needs an admin-maintained normalisation layer:

- raw label
- corrected label
- abbreviation
- cohort
- order

This should flow into:

- search results
- role detail
- mapping assistant
- filters

## Dashboard concept

The dashboard should orient the user quickly.

Possible dashboard cards:

- Upload a PD
- PDs awaiting validation
- Search existing roles
- Open Mapping Assistant
- Admin tools

Useful summary metrics:

- total PDs in database
- validated PDs
- unvalidated PDs
- mapped PDs
- validated mappings
- latest workbook import

Dashboard should prioritise action, not analytics.

## Role detail page

A role detail page should show:

- role title
- PD ID
- classification/grade
- validation status
- mapping status
- source document link
- structured extracted sections
- capability information
- current job family mapping
- similar roles entry point
- mapping assistant entry point

The page should make it clear whether the data has been human validated.

## Validation page design

The validation screen is text-heavy and should support focused review.

Recommended pattern:

- left or top summary panel
- sections stacked vertically
- each section has review status
- editable fields
- add/remove rows where applicable
- save draft
- validate entire PD
- open Word source

Sections may include:

- role details
- primary purpose
- key accountabilities
- key challenges
- key relationships
- essential requirements
- capabilities

No section should block validation merely because it is empty. Some PDs are legitimate exceptions.

## Mapping Assistant design principles

The Mapping Assistant is the most important decision-support interface.

It should:

- reduce cognitive load
- start broad, then drill down
- show evidence without overwhelming the user
- make validated evidence obvious
- show classification/grade context
- distinguish “similar work” from “same business domain”
- avoid implying that the model is always correct

Suggested wording:

> The assistant suggests likely mappings based on similar roles and framework definitions. Use these suggestions as evidence; the final mapping remains a human decision.

## Status language

Use consistent labels:

- Uploaded
- Extracted
- Needs review
- Draft saved
- Validated
- Unmapped
- Mapping suggested
- Mapped
- Mapping validated

## Accessibility requirements

Design should support:

- high contrast
- keyboard navigation
- readable font sizes
- clear focus states
- semantic headings
- table readability
- non-colour-only status indicators

## Visual style guidance

Suggested style:

- white/light grey background
- deep purple or navy accent
- green for validated/success
- amber for needs review/draft
- red only for errors
- restrained cards
- clear tables
- generous spacing

The design should feel like a reliable internal government tool, not a sales dashboard.

## Sanitised sample content

Use fake examples like these:

### Example PD

- PD ID: `12345-01`
- Role title: `Asset Data and Reporting Analyst`
- Classification: `TWL7`
- Status: `Validated`
- Current mapping: `Infrastructure > Strategic Asset Planning > Asset Information and Data`

### Example semantic search query

> "creates reports, analyses data, and communicates insights to stakeholders"

### Example job family options

- Infrastructure
- Analytics and Reporting
- Information Technology

### Example similar roles

- `12340-01 Asset Data and Information Manager`
- `12341-01 Reporting Analyst`
- `12342-01 Business Intelligence Developer`

## What not to upload into Stitch

Do not upload:

- real PD documents
- real employee or organisationally sensitive content
- full databases
- actual source code unless approved
- confidential workbook data unless approved

Use this brief plus sanitised examples instead.

## Desired output from Stitch

Ask Stitch to produce:

1. A clean app information architecture
2. Wireframes for the core screens
3. A visual design direction
4. A dashboard layout
5. A validation review screen
6. A Mapping Assistant flow
7. Admin screen concepts

Most important screen to design well:

> Mapping Assistant

Second most important:

> Validation review workflow

## Suggested prompt to paste into Stitch

Design a professional, accessible web application for an internal government Position Description Management System.

The application lets users upload Word position descriptions, review and validate extracted structured fields, store validated PDs in a database, search existing roles, and use a Mapping Assistant to suggest job family mappings based on similar mapped roles and framework definitions.

The app should feel trustworthy, calm, readable, and suitable for public-sector HR/workforce users. It should support human judgement rather than looking like a fully automated black box.

Please design:

- dashboard
- upload PD screen
- validation queue
- validation review page
- role search
- role detail
- Mapping Assistant
- admin screens for classifications and framework/mapping workbook import

The Mapping Assistant should start by showing the top recommended job families, then allow the user to click into a job family to review likely sub-families/specialisations and similar mapped roles used as evidence. It should show classification/grade context and whether evidence mappings are validated.

Avoid overwhelming users with the full framework at once. Use progressive disclosure, clear status indicators, and accessible tables/forms.

