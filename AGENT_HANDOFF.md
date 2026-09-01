# Agent handoff

Use this prompt after cloning the repository:

```text
Open this repository and read AGENTS.md first. Run:

python -m research_semantic_ledger doctor

If doctor passes, run the summary command it returns and then run:

python -m unittest discover -s tests -v

Report the verified public capabilities and their boundaries before making changes. Do not request API credentials or search for private artifacts unless I explicitly place them in scope. For any implementation request, preserve evidence links, keep generated records in candidate state, add or update dependency-free tests, and rerun doctor plus unittest before declaring completion.
```

Expected first-run outcome: doctor returns JSON with `status: "pass"`, the sample summary reports two bindings, two claims, and two relations, and all unit tests pass.
