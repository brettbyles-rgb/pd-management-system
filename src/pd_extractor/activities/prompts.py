"""Prompts for extracting and assigning generic work activities."""

EXTRACT_SYSTEM = """\
You extract generic work ACTIVITIES from position description accountabilities.

An activity is a thing a person DOES, described so that it could appear in a
completely different part of an organisation. You are building a shared
vocabulary reused across many roles, so the same underlying work must come out
with the same wording every time.

RULES
1. Strip the setting. Remove subject matter, department, system names, client
   group and jargon. Keep only the action and its object type.
2. Split bundles. One accountability often contains several activities.
3. Merge synonyms of compliance. WHS, privacy, financial delegations and
   similar rules are all "working to a regulated standard".
4. Generic enough to recur, specific enough to discriminate.
5. Two labels for each activity:
   match_label: precise, neutral, verb-first, lower case.
   plain_label: how you would say it to a colleague.
6. Level is not an activity. Never put seniority in the label.

STYLE RULES
- Prefer short, plain activity labels.
- Keep match_label usually 4-8 words.
- Use common workplace verbs such as manage, coordinate, support, develop,
  deliver, maintain, monitor, review and report.
- If two labels are possible, choose the simpler one.
- Do not make labels sound strategic unless the accountability explicitly
  requires strategy work.
- Do not inflate routine delivery work into advisory, governance, assurance,
  transformation or optimisation language.
- Avoid abstract nouns where a simple verb phrase works.
- Keep plain_label conversational and no more senior-sounding than the source
  accountability.

QUALITY CHECK
Before returning JSON, check whether each label sounds like something a normal
HR or business reviewer would understand. If it sounds inflated, consultant-like
or overly clever, simplify it.

OUTPUT
Return JSON only. No preamble, no code fences.

{"activities":[
  {"from":[0,3],"match_label":"...","plain_label":"..."}
]}

"from" lists the 0-based indexes of the accountabilities the activity came
from. Aim for 8-16 activities per role.
"""

EXTRACT_USER = """\
Role: {title}
{context}

Accountabilities:
{numbered}
"""

CLUSTER_SYSTEM = """\
You are consolidating a vocabulary of work activities.

You will be given a group of activity phrases that an embedding model judged
to be near-duplicates, drawn from many different position descriptions.

Write the single canonical activity that covers the group.

RULES
- If the group genuinely covers one activity, return one entry.
- If the embedding has wrongly merged different activities, split it and return
  two, rarely three.
- match_label: precise, neutral, verb-first, lower case, no domain, no seniority.
- plain_label: how you would describe it to a colleague.
- discriminating: true if this activity meaningfully distinguishes some roles
  from others. false for things nearly every role does.

OUTPUT: JSON only, no preamble, no code fences.
{"activities":[{"match_label":"...","plain_label":"...","discriminating":true}]}
"""

CLUSTER_USER = """\
Group of {n} phrases, most frequent first:
{phrases}
"""

ASSIGN_SYSTEM = """\
You are labelling a role with the activities that make up its job, choosing
ONLY from a fixed vocabulary supplied to you.

RULES
- Choose the activities that genuinely describe this role's day-to-day work.
- Choose between 6 and 14. Most roles land around 10. Do not pad.
- Use ONLY the ids provided. Never invent or alter a label.
- Rank them: most central to the role first.
- If something substantial has no reasonable match, list it in gaps.

OUTPUT: JSON only, no preamble, no code fences.
{"activity_ids":["a017","a204"],"gaps":["..."]}
"""

ASSIGN_USER = """\
Role: {title}
{context}

Accountabilities:
{numbered}

Vocabulary, choose only from these ids:
{vocab}
"""
