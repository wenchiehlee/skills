---
name: skill-company-reputation-research
description: Collect and synthesize public Taiwan and global jobseeker intelligence about a specified company, including workplace reputation, interview experience, salary signals, labor disputes, layoffs, public records, and recurring red flags. Use when the user provides a company name and asks to research company background, employer reputation, jobseeker reviews, interview/salary transparency, or 「起底公司真實內幕」 before applying, interviewing, or accepting an offer.
---

# Company Reputation Research

Use this skill to produce an evidence-based employer reputation brief for a specified company. Work only from public or user-provided sources. Do not present anonymous claims as facts. Separate verified records, repeated firsthand reports, isolated allegations, and unresolved rumors.

For channel selection and query patterns, read `references/source-map.md`.

## Inputs

Require at least:

- Company name
- Target market or location, if known
- Role/function, if relevant

If the company name is ambiguous, identify likely legal entities, brands, subsidiaries, Chinese/English aliases, and office locations before researching.

## Research Workflow

1. Normalize the company identity:
   - Official company name
   - Brand names
   - Chinese/English aliases
   - Taiwan tax ID, stock code, or ticker, if available
   - Headquarters and target office location

2. Search jobseeker channels:
   - Prioritize Taiwan channels for Taiwan jobs or Taiwan entities.
   - Prioritize global channels for multinational, overseas, or English-language roles.
   - Search both local-language and English names when the company is multinational.

3. Search official and semi-official records:
   - Company registry
   - Public filings and investor relations
   - Taiwan MOPS, TWSE, or TPEx if listed
   - Labor-law violation announcements where available
   - Court judgments or administrative sanctions where available
   - Credible news articles

4. Triangulate signals:
   - Count source types, not only post volume.
   - Give more weight to recent, specific, role-relevant, firsthand reports.
   - Discount vague one-off comments, copied posts, obvious review stuffing, and claims without time, role, or location context.
   - Flag a pattern only when multiple independent sources point to the same issue.

5. Preserve uncertainty:
   - Label anonymous/forum content as anecdotal.
   - Mark paywalled or partially visible sources as partial evidence.
   - Avoid naming private individuals unless they are public company officers or already central to public records.

## Output Format

Produce the report in Traditional Chinese unless the user requests otherwise.

Include these sections:

1. `公司識別`
   - Official/legal name, aliases, location, industry, website, stock/ticker if any

2. `資料來源總覽`
   - Table with source, coverage, latest observed date, access limits, and credibility notes

3. `求職者常查管道`
   - Taiwan channels
   - Global channels
   - Which channels had useful results for this company

4. `重點發現`
   - Interview process
   - Salary/compensation
   - Working hours/overtime
   - Management/culture
   - Turnover/layoffs
   - Legal/labor/public-record signals

5. `風險分級`
   - High / Medium / Low / Unknown
   - Explain evidence quality and uncertainty

6. `面試前建議追問`
   - Concrete questions the candidate should ask
   - Contract, pay, overtime, bonus, probation, non-compete, and job-scope details to verify

7. `引用來源`
   - Link every material claim to sources
   - Mark anonymous/forum claims clearly

## Evidence Rules

- Do not scrape private or access-controlled data.
- Do not bypass login, paywall, robots, or anti-abuse mechanisms.
- Do not repeat defamatory claims as facts. Attribute them as reports or allegations and state whether they are corroborated.
- Prefer direct source links over search snippets when available.
- Use exact dates for time-sensitive claims such as layoffs, legal disputes, and recent reviews.
