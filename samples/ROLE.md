# Sample role — Senior Backend Engineer

Demo material for trying the app. Nothing here is seeded into the database;
create the role yourself and paste or upload the resumes.

**Description**

> Owns our payments and billing services. Works close to the data model and is
> comfortable operating what they ship.

**Requirements**

| Requirement | Weight       | Also counts as         |
| ----------- | ------------ | ---------------------- |
| Python      | Must have    |                        |
| PostgreSQL  | Must have    |                        |
| Docker      | Important    | containers             |
| Kubernetes  | Important    |                        |
| REST API    | Nice to have |                        |
| Terraform   | Nice to have | infrastructure as code |

## What you should see

Add all eight resumes and the ranking comes out like this:

| Score | Candidate    | Reading                                            |
| ----: | ------------ | -------------------------------------------------- |
|   100 | Priya Nair   | Names every requirement. The uncontroversial hire.  |
|    92 | Lena Fischer | Platform specialist; no REST API work.             |
|    92 | Arjun Desai  | Data engineer; no Terraform.                       |
|    83 | Tomas Novak  | **Look at this one** — see below.                  |
|    75 | James Osei   | Solid, no Kubernetes or Terraform.                 |
|    75 | Elena Rossi  | Graduate. Same score as James, very different case. |
|     0 | Sam Okafor   | Frontend engineer. Correctly ranked last.          |
|     0 | Marcus Webb  | **Look at this one too** — see below.              |

Open any candidate to see the evidence table: every point traces to a quoted
span of their own resume.

## Two cases worth sitting with

Both of these are the point of the demo. Neither is a bug.

### Marcus Webb scores 0, and is probably the second-best candidate

Marcus has fourteen years on transaction systems. He also never writes a single
keyword. He says *"the language we standardised on for backend work"* instead of
Python, *"the relational store underneath it"* instead of Postgres, *"our
container orchestration layer"* instead of Kubernetes, and *"the
resource-oriented HTTP interface"* instead of REST API.

Keyword coverage cannot see any of it. He scores 0 and sorts below a frontend
engineer.

Try the fix: add aliases for his phrasings — `relational store` on PostgreSQL,
`container orchestration` on Kubernetes and Docker, `resource-oriented HTTP` on
REST API, `declarative infrastructure` on Terraform. Save, and he jumps
**0 → 75**.

Then notice what is still missing. Python stays unmatched at 0, and no alias
fixes it, because Marcus never names the language anywhere in the document.
There is nothing for a matcher to match. Recovering that requires inferring
from *"since the 2.x days"* and the surrounding context — which is reading
comprehension, not string matching.

That is the honest boundary of this approach, and it is why the score is
presented as a **sort order with its reasoning attached**, never as a verdict.
The recruiter reading Marcus's evidence table sees six empty rows and can tell
immediately that what is missing is *words*, not *experience*.

### Tomas Novak scores 83 and should not be shortlisted

Tomas is an engineering manager who says plainly that he has not shipped a
production feature since 2021. Every requirement appears in his resume, so he
scores well — coverage cannot distinguish *"I set the technical direction"* from
*"I wrote it"*.

This is the second structural limit: **coverage is not depth**. One passing
mention scores exactly the same as eight years of daily use.

Both cases argue the same thing: the tool's job is to get eight resumes into a
defensible order with the reasoning on screen, so a human spends their attention
where it is worth spending. It is not to make the decision.
