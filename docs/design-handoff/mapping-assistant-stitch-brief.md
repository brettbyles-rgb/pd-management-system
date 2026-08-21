# Mapping Assistant design brief for Google Stitch

## Product context

We are building a Position Description Management System for an internal government workforce context.

The system turns Word position descriptions into structured, validated data, then uses that data to help users search roles and assign job family mappings.

The Mapping Assistant is not intended to make the final decision automatically. It should support a human reviewer by showing ranked suggestions, similar mapped roles, and enough evidence to make a defensible mapping decision.

## Core user problem

Users need to map a position description into a large, multi-layered job family framework.

The framework has:

- job families
- sub-families
- specialisations
- codes
- definitions
- exclusions

Users may not know the framework well. The interface should therefore guide them gently from broad options to more specific options, without overwhelming them with all levels at once.

## Desired interaction model

The Mapping Assistant should feel like a guided review workflow, not a dashboard.

The user starts with one PD, then moves through:

1. review the selected PD summary
2. inspect the top recommended job families
3. drill into likely sub-families
4. inspect likely specialisations if relevant
5. mark plausible options for review
6. compare marked options
7. assign the final mapping

## Important design principles

- Calm, simple, government-style interface.
- Progressive disclosure: show the next layer only when the user asks for it.
- Avoid dense dashboards, charts, and noisy metrics.
- Avoid making the user scroll up and down to understand one decision.
- Make the hierarchy obvious: job family → sub-family → specialisation.
- Show evidence, but keep it secondary to the mapping workflow.
- The tool recommends; the human decides.

## Recommended screen structure

### Header / selected PD summary

Show:

- PD ID
- role title
- classification/grade
- current mapping status
- whether mapping is validated

This area should remain compact.

### Recommended job families

Show only the top few job families initially.

Preferred behaviour:

- show two or three job families at a time
- allow the user to cycle through additional families
- each card/row should show the family name, rank, overall score, and short evidence summary

### Sub-family drill-down

When a job family is selected, show the top sub-families under that job family.

The user should not need to understand the whole framework tree at once.

### Specialisation drill-down

When a sub-family is selected, show up to three likely specialisations that meet the minimum score threshold.

Specialisations should appear in a clear detail panel or adjacent column, not far down the page.

The user should be able to click outside the detail panel or choose another sub-family to move on.

### Marked for review

Users can mark job family, sub-family, or specialisation options for review.

Marked items should appear in a small review basket.

Clicking a marked item should:

- show its detail
- update the evidence roles to match that item
- prepare the user to assign that mapping if they are satisfied

### Evidence roles

Show similar mapped roles as evidence.

Evidence rows should include:

- role title
- PD ID
- classification/grade
- similarity score
- mapped job family/sub-family/specialisation
- whether the mapping was validated

Evidence should be filtered based on the currently selected or marked option.

## Ranking logic to communicate visually

The app blends:

- similar mapped-role evidence
- framework-definition match
- grade/classification proximity

The UI should not over-explain the maths. It should say enough for trust:

> Ranked using similar mapped roles, framework definitions, and grade proximity. Final mapping remains a human decision.

## Tone and visual style

Preferred:

- restrained government service style
- clear cards or rows
- lots of whitespace
- readable typography
- navy/purple accent
- subtle borders
- no heavy dashboards

Avoid:

- cramped sidebars
- large KPI panels
- too many metrics at once
- boxy/cluttered admin-dashboard patterns
- excessive colour
- floating elements that obscure context

## Sample content

Selected PD:

- PD ID: 10045-02
- Role title: Support Officer
- Classification: TWL4
- Current mapping: Business Support

Example recommended job families:

1. Business Support
2. Program and Project Management
3. Information Technology

Example sub-families:

- Administration
- Executive Support
- Program/Project Auxiliary and Support
- IT Support and Service Management
- IT Infrastructure and Operations
- IT Project Management

Example specialisations:

- Systems Administration
- IT Program/Project Management

## What we want from Stitch

Produce a clean UI concept for the Mapping Assistant screen only.

Focus on:

- hierarchy
- progressive disclosure
- reduced clutter
- easy comparison
- clear human decision point

Do not produce a full analytics dashboard.

