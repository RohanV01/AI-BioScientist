# PhD Application Strategy, Anchored on This Project

`docs/19-research-publication-readiness.md` covers how to make this project's *research* credible.
This doc is the next question: how to use it to choose which PhD programs to target and, more
specifically, which labs to apply to — since for a fully-funded PhD, the lab/advisor decision
matters more than the university's brand name. Getting this wrong (applying broadly without
targeting) is the single most common reason a strong applicant doesn't get funded offers.

**Core premise, stated up front:** a fully-funded PhD offer is really an advisor deciding to spend
their grant money on you. The application system (department, brand, ranking) is secondary to that
one relationship. Everything below is in service of finding the 10-20 advisors for whom this
project is genuinely relevant work, not a generically impressive project.

## Part 1 — What this project actually tells you about program fit

Before searching for labs, be honest about what this project *is*, since that determines which
department/field it belongs in — this project doesn't cleanly sit in one:

- **The mechanism (grounding enforcement on tool-using LLMs)** is a trustworthy-AI / NLP
  contribution — fits CS departments, specifically NLP or ML-for-reliability groups.
- **The application domain (biomedical research tools)** is a bioinformatics / biomedical
  informatics contribution — fits biomedical informatics, computational biology, or health
  informatics departments.
- **The evaluation methodology (benchmark + human expert scoring)** is itself close to
  human-AI-interaction / evaluation-science work — fits some HCI-adjacent AI labs too.

Don't force this into only one bucket. Apply to labs across all three framings and let the
benchmark result (once it exists, per `docs/19`) decide which framing you lead with per
application — the same project, framed differently, is a legitimate fit for all three.

### Program-model dimension (decide this before searching for labs)

- **US PhD (CS / bioinformatics / biomedical informatics departments):** admission is committee-run
  but funding is usually advisor-tied (RA-ships off a grant). A strong project + a specific
  advisor's interest can outweigh a mediocre GPA or no master's. This is generally the best fit for
  someone coming in with a strong self-directed project and no formal research pedigree yet.
- **UK/EU PhDs:** often structured as pre-defined, already-funded studentships tied to a named
  project description, not a general "apply to the department" pool. Search for open studentships
  matching this project's themes specifically (see search terms below) rather than only faculty
  pages — the funding line often exists before the student does.
- **Direct doctoral programs at industry-adjacent institutes** (Max Planck, ELLIS network in
  Europe, Vector Institute in Canada, Allen Institute-affiliated programs in the US) — worth
  including since they're often better-funded and more research-focused than a standard university
  department, and trustworthy-AI/AI-for-science is squarely in their wheelhouse.

## Part 2 — Methodology to find the right labs (the actual process)

This is a literature-search problem, and this project already has the tooling to do it well — use
OpenAlex the same way `app/tools/literature_discovery.py` does, rather than manually browsing
Google Scholar one query at a time.

### Step 1 — Build seed search terms from the project itself

Pull these directly from what's actually been built, not generic AI buzzwords:

- "grounded generation" / "attributed question answering" / "faithfulness" + "large language models"
- "tool-augmented language models" / "tool-use agents" / "LLM agents" + "reliability" or "trust"
- "retrieval-augmented generation" + "citation verification" or "hallucination detection"
- "LLM" + "scientific discovery" or "biomedical research assistant" or "AI co-scientist"
- "human-AI trust" + "large language models" + "expert evaluation"

### Step 2 — Pull recent papers per term, programmatically

Use OpenAlex's free, unauthenticated works-search API (same approach as `discover_papers` in this
codebase, and the same one flagged in your own [[reference_openalex_api_gotcha]] memory — stay
unauthenticated for this kind of bulk search, the $1/day key cap will bite you fast doing 5+ broad
queries). For each search term: pull the last 2-3 years of papers, sorted by citation count and
recency, and extract:

- Author names and their listed institutional affiliation (OpenAlex returns this directly)
- The paper's own citation count (a rough proxy for how active/influential that specific line of
  work is right now)
- Whether the same author/lab recurs across multiple of your search terms — that recurrence is a
  much stronger fit signal than any single paper matching once

This is mechanical enough that it's worth literally scripting (a one-off script against OpenAlex,
not a wired platform tool) rather than doing by hand in a browser — you'll want to re-run it every
few months as new papers appear before application deadlines.

### Step 3 — Build a lab shortlist spreadsheet, not just a paper list

For every author who recurs across 2+ searches, add a row with:

| Field | Why it matters |
|---|---|
| Advisor name + institution | the actual target |
| Department (CS / bioinformatics / biomedical informatics / HCI) | which framing of this project to lead with |
| 2-3 most relevant recent papers | what to cite in the outreach email |
| Lab website "prospective students" status | many labs state directly whether they're recruiting/funded for the next cycle — check before spending time on an email |
| Recent PhD student output (do their past students publish, graduate, get good placements?) | a proxy for whether the lab is actually a good place to do a PhD, not just a name match |
| Funding signal (recent grant announcements, lab size, how many current PhD students) | a large, well-funded, actively-growing lab is a safer bet for a *fully funded* offer than a single-PI lab running on one small grant |
| Personal-fit signal (do they have public talks, podcasts, blog posts about their research philosophy?) | tells you whether their day-to-day working style would suit you, and gives you real material to reference in outreach beyond just their papers |

Aim for 15-25 real candidates at this stage, not 100 — depth of fit beats breadth of applications
for funded-PhD outcomes specifically.

### Step 4 — Rank by genuine overlap, not prestige

Score each candidate on:
1. **Direct topical overlap** with this project's actual mechanism or evaluation (not just "AI").
2. **Active funding + recruiting status** — a perfect topical match who isn't taking students next
   cycle is not a real candidate this round.
3. **Track record placing PhD students** — check their last 3-5 graduated students' current roles.
4. **Reachability** — mid-career faculty at strong-but-not-hyper-famous labs often reply to cold
   email and have more bandwidth than a handful of superstar names everyone else is also emailing.

Sort into three tiers: **strong fit + funded + reachable** (apply here first, invest the most time
per email), **strong fit but competitive/uncertain funding** (apply, but don't over-invest), and
**topical fit only, no other signal yet** (lower priority, worth a light-touch email only).

### Step 5 — Outreach, timed correctly

- Email 2-4 months before the program's application deadline — early enough that a "yes, I'm
  taking students and this is interesting" response can actually shape which program you formally
  apply to, not after the decision is already effectively made.
- Structure: one paragraph on why their specific recent work connects to what you built (name the
  paper), one paragraph on the project itself with the concrete result if you have one by then (per
  `docs/19` — lead with the finding, not the platform), and a direct, specific question ("are you
  taking students for Fall/Michaelmas/etc. intake, and would this be relevant to your group's
  direction?"). Attach the preprint/repo link, don't paste the whole project into the email body.
- Track responses in the same spreadsheet — a lab that replies thoughtfully, even declining, is
  worth more future attention than one that ignores you; a lab that ignores a well-targeted email
  is itself a signal about fit.

## Part 3 — Red and green flags once you have a candidate lab

**Green flags:**
- Advisor has multiple current grants (check public grant databases: NIH RePORTER for US
  biomedical funding, NSF award search, UKRI Gateway to Research for UK) — funding security for
  the multi-year duration of a PhD, not just at the moment of admission.
- Recent graduated students hold roles you'd actually want (faculty positions, strong industry
  research roles, not just "employed somewhere").
- Lab publishes at a steady cadence with multiple co-authors per paper (signals a functioning,
  collaborative group, not one overloaded PI).
- Advisor or lab has public material (talks, a lab blog, interviews) discussing mentorship style,
  not just research output — gives you real signal on fit beyond the papers.

**Red flags:**
- No funding announcements in the last 1-2 years, or the lab's own site is stale/unmaintained.
- High PhD student turnover, or public complaints findable via a quick search (Glassdoor-style
  academic forums, department Reddit threads) — worth 10 minutes of checking before investing weeks
  in an application built around one specific advisor.
- A single-PI lab with no other students or postdocs — higher risk for a "fully funded" guarantee
  holding for the entire program duration, since funding is often tied to one grant with a fixed
  end date.

## Part 4 — Concrete checklist and timeline

1. **Now → finish the evaluation in `docs/19`** — this is the asset that makes every email in Part
   2/Step 5 land differently. Don't start heavy outreach before at least a preliminary result
   exists.
2. **In parallel, run the OpenAlex seed search (Part 2, Steps 1-2)** — this doesn't depend on the
   evaluation being done and can start immediately.
3. **Build the shortlist spreadsheet (Step 3)** once the seed search has a few dozen recurring
   names — target 15-25 real candidates.
4. **4-2 months before target application deadlines:** send outreach emails to the top tier,
   preprint/result attached if ready, project repo link if not.
5. **Formal applications:** apply broadly enough to hedge (aim for 6-10 programs across the US/UK/EU
   mix from Part 1), but weight your personal statement and any "faculty of interest" field toward
   the advisors who actually responded with interest — that's a much stronger signal to a committee
   than a generic "your department is excellent" statement.

## Related

- `docs/19-research-publication-readiness.md` — the evaluation and preprint this whole strategy
  assumes exists (or is close to existing) before outreach starts. Read that doc's steps 1-7 first;
  this doc is what to do with the result, not a substitute for producing one.
