# Default Prompt

When a repository is not explicitly mentioned, use `derekyim/agent-quality-helper`. Always assume there is no organization, just this users account.  Here the public name for agent-quality-helper is "evalgenie" or "Evalgenie", use them as synonyms.

if there are questions on features/functionality there is a docs/prd_source/evalgenie_prd_final.md containing the product requirements for this repository.

There is a 'build team' repo that defines the workers and build team for this repo `derekyim/evalgenie-build-team`.  A number of personas exist to build out the application, they have read the prd and are up to date on how to build.


there is no configured linear or slack integration, the workflow is as follows:

evalgenie-build-team has a series of tasks.
        ↓
These tasks will be made into GitHub issue in agent-quality-helper
        ↓
each task mentions @openswe
        ↓
open-swe-dysprosium-harness checks out agent-quality-helper
        ↓
agent reads PRD + docs + code
        ↓
agent opens PR against agent-quality-helper