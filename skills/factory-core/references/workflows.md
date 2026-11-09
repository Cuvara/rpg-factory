# Workflow planning

When the task routes to a non-engineering domain or spans domains, create a workflow spec and use `factory-workflow.py plan`, then dispatch ready nodes by wave (`dispatch`); use `status` while work lands and `report` for delivery. The CLI and schema are documented in `docs/workflows.md` and `docs/schemas/workflow.schema.json`.

Route artifact kinds from the registry. Engineering targets require a registered repo and repo-relative paths. Dispatch contracts carry artifact IDs and blob revisions, allowed writes, domain checks and acceptance criteria. Dispatch only ready nodes and never approve artifacts; missing trusted approval evidence is HUMAN_REQUIRED. See `skills/delivery/references/delivery.md` for lead and worker roles (RPG additions: `references/parallel-work.md`); an Engineering `implementation` node goes through the same
delivery pipeline (delivery.md section 10: cross-model review, QA, READY_FOR_PR).
