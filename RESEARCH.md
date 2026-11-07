# Research behind Lipso

Research date: **7 November 2026**. Public Hacker News submissions were retrieved through the Algolia API. Counts below are observations from that retrieval, not estimates of customers, market size, or willingness to pay. Original titles and submission text were read; this is not an exhaustive competitor or patent search.

## Needs investigated

| Need | Public evidence | Signal and limits |
| --- | --- | --- |
| Private search across sensitive documents | [“I have many PDFs – what is the best local way to leverage AI for search?”](https://news.ycombinator.com/item?id=40528192) | 257 points, 90 comments. The request explicitly describes sensitive bills, tax documents, local processing, and avoiding manual tags. Strong discussion engagement, not purchase validation. |
| Managing records across a household | [“How do you manage your ‘family data warehouse’?”](https://news.ycombinator.com/item?id=37520374) | 127 points, 135 comments. Records span finance, health, insurance, warranties, maintenance, and family members. This supports a cross-domain problem. |
| Owning a durable document system | [Paperless-ngx discussion](https://news.ycombinator.com/item?id=37800951) | 627 points, 182 comments. Substantial interest in an existing open-source solution. Evidence against claiming document organization is a new category. |
| Private local models and documents | [“Recommendations for Local LLMs in 2024: Private and Offline?”](https://news.ycombinator.com/item?id=39952114) | 48 points, 29 comments. Privacy and offline operation matter to some users. Lipso avoids a model dependency and documents the resulting language limitations. |
| Planning variable household cash flow | [“How do you manage your household cashflow?”](https://news.ycombinator.com/item?id=32190687) | 16 points, 26 comments. The submission asks about variable income, fixed and variable expenses, annual obligations, and shared accountability. Specific pain; relatively small sample. |
| Continuity and ownership in finance software | [Mint shutdown discussion](https://news.ycombinator.com/item?id=38114512) | 145 points, 178 comments. Shows attention to finance-tool transitions. Does not prove demand for this particular replacement. |
| Connecting documents, work, quotes, and expenses | [“How do you manage projects at home?”](https://news.ycombinator.com/item?id=38774742) | The submission explicitly requests tasks, calendar/reminders, quotes, expense tracking, notes, and document management, with offline/self-hosted access. Only 2 points and no comments: useful qualitative fit, weak popularity evidence. |
| Private documents plus deadlines | [“Personal Task/File Management”](https://news.ycombinator.com/item?id=31012986) | Explicit request for secure local documents, task deadlines, and device access. 3 points, no comments; corroborating anecdote only. |
| Task planning across daily life | [“How Do You Manage and Schedule Everything in Your Life?”](https://news.ycombinator.com/item?id=36493990) | 13 points, 13 comments. Supports the general need, not a unique algorithm or product opportunity. |
| Personal relationship management | [“Personal CRM for individuals?”](https://news.ycombinator.com/item?id=1599944) | 19 points, 5 comments; repeated related questions also appeared. Left outside this build because contacts without a strong relationship to the evidence-to-plan workflow would expand surface area without improving the central result. |

## Existing work found

The search found clear prior art. These categories are not unbuilt:

- **Document management:** Paperless-ngx, plus many document-chat systems. [PocketLLM discussion](https://news.ycombinator.com/item?id=39618125) describes private document search and question answering.
- **Cross-application search:** [Needl launch](https://news.ycombinator.com/item?id=34598406), 106 points and 75 comments, describes search across documents, messages, and apps.
- **Local financial planning:** [FinP4l](https://news.ycombinator.com/item?id=46093210) explicitly describes local scenario modeling. [FinBodhi](https://news.ycombinator.com/item?id=45800117) describes local multi-currency, double-entry finance. [Budgetist](https://news.ycombinator.com/item?id=45537796) describes local budgeting and data ownership.
- **Provenanced contradiction detection:** [A CozoDB fork discussion](https://news.ycombinator.com/item?id=48605896) explicitly describes versioned facts and cross-document contradictions for agent memory.
- **Personal CRM:** Relevant discussions point to Monica and other existing tools.
- **Scheduling:** Deadline/effort/capacity-based scheduling appears even in [an older startup-idea discussion](https://news.ycombinator.com/item?id=3563031). It is not a new invention.

## The integration hypothesis

**People managing projects with variable income may benefit from one inspectable chain from source documents to commitments to feasible work to cash consequences.**

The useful experiment is not another search box or budget chart. It is the connection:

1. An agreement states an amount or date, retained as an exact quote.
2. A revision changes the term or an invoice disagrees. The system keeps both pieces of evidence and flags the disagreement.
3. A user links a reviewed term to a task or cash-flow assumption.
4. The dependency scheduler calculates a completion date under limited daily capacity.
5. A linked receipt shifts with the completion date, changing the cash forecast.
6. A user tests a different capacity, expense level, or delay as a separate scenario.
7. Source changes and missing evidence remain visible in the plan instead of being silently overwritten.

Lipso implements that chain locally, with explicit assumptions and no remote model dependency. That is a product hypothesis about a useful combination. It is **not evidence that no other product has ever implemented it**, and “monstrous singularity” is not a technical capability claim.

## What has and has not been validated

Implemented and tested: the technical chain above, import/search/review workflows, explicit time semantics, task-dependent payments, reproducible simulation, saved branching, evidence drift, export, and internal integrity checks.

Not validated: demand for the exact bundle, willingness to pay, superiority over existing products, effectiveness for real legal interpretation, extraction accuracy on representative multilingual or scanned documents, real-world calibration of financial risk, or safe use as a multiuser hosted service.

A focused pilot would recruit independent professionals who currently juggle contracts, project tasks, and cash spreadsheets. Measure whether they can identify a conflicting term, trace a forecast to its source, and understand the cash impact of a delayed delivery faster and with fewer errors than their current process. That is a more useful next test than adding unrelated modules.
