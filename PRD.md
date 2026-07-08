# Kept, product requirements

Status: living doc for the Slack Agent Builder Challenge build. Deadline 13 Jul 2026.

## Problem

Agencies and client teams live in Slack Connect channels with their clients.
Promises get made in threads all day ("we'll send the revised deck Friday").
Nobody converts a thread reply into a tracked task, so there is no record of what
was promised. The client notices the missed deadline before the team does, and
trust erodes one slipped promise at a time. The place commitments die is exactly
where they were born: a Slack thread that scrolled away.

## Who it is for

The account manager or delivery lead at a small agency or consultancy, working in
Slack Connect channels with clients. Buyer persona: agency ops lead who feels
client churn directly.

## What it does

1. Catches commitments as they are made, and asks the promise-maker to confirm with one tap.
2. Keeps a Promise Ledger as a Slack canvas in the channel itself. No separate app.
3. Nudges the owner privately before a deadline.
4. Drafts the honest delay message for the client channel when a promise slips.
5. Drafts the weekly client update from the ledger, and answers recall questions
   ("what did we promise this client?") live, with links to the source threads.

## Scope for the hackathon

Must have (the demo fails without these):

- Detect a commitment in a channel message and post a private confirm card.
- On confirm, store the promise and render the ledger canvas in the channel.
- Nudge the owner before the due date.
- Draft the delay message when the owner needs more time.
- Recall: answer "what did we promise this client" with citations.

Should have if time allows:

- Weekly client update draft in the agent panel.
- Reschedule tracking and a second-reschedule escalation note.
- An App Home tab showing all promises across channels.

Won't do (out of scope for this build):

- Auto-sending any client message without a human confirm.
- Multi-workspace distribution or a Marketplace listing.
- Calendar-aware natural date parsing beyond what the LLM resolves.
- Analytics dashboards, billing, accounts.

## Success is the demo

The 3-minute video shows, in order: a promise made in a client channel, the
confirm card, the ledger updating, the deadline nudge, the drafted delay message,
and a recall answer with citations. Every step runs live in the sandbox. The
architecture slide states: the LLM only classifies, every action needs a human
tap, and no raw Slack content is stored outside Slack.

## Non-goals and honest limits

Kept detects promises with an LLM plus a human confirm, so precision is a UX
decision not a model guarantee. It stores only confirmed structured promises,
never raw messages. See ENGINEERING.md for the full security posture.
