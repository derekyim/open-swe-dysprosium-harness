# Default Prompt — &lt;Your Product Name&gt;

Replace the placeholders in this file with your product context. The
harness will inject this content into the agent's system prompt as a
"Custom Instructions" block on every run.

## Product context

- **Product name:** &lt;e.g. EvalGenie / Acme Sidecar&gt;
- **Product repo:** `&lt;owner/repo&gt;`
- **Public synonyms** the agent should treat as the same product:
  &lt;e.g. "Foo", "Foo Cloud", "the sidecar"&gt;
- **PRD / spec location:** `&lt;path/in/product/repo/to/prd.md&gt;`

## Triggering surface

Pick whichever applies and delete the others:

- **GitHub-issue triggered:** when a user mentions one of
  `OPEN_SWE_MENTION_TAGS` on a GitHub issue or PR comment, the agent
  picks up the issue body and operates on the product repo.
- **Linear-triggered:** issues in Linear project &lt;X&gt; map to the
  product repo &lt;owner/repo&gt;.
- **Slack-triggered:** mentions in channel &lt;#name&gt; route to the
  product repo &lt;owner/repo&gt;.

## Conventions specific to this product

- &lt;Linting/formatting commands beyond `make format`&gt;
- &lt;Test command(s) for the most relevant subset of tests&gt;
- &lt;Branch naming&gt;
- &lt;Anything the agent should never touch (auth flows, schema migrations, …)&gt;
