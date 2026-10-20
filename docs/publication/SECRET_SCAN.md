# Secret scan

Run this from the repository root before any publish. It works both before the first commit
(no `git ls-files` yet) and after it.

## 1. Built-in scan (no extra tools)

```bash
# Files that would be published: tracked files plus untracked, not ignored files.
{ git ls-files; git ls-files --others --exclude-standard; } | sort -u > /tmp/veritas-publish-set.txt
wc -l < /tmp/veritas-publish-set.txt

# PEM private keys and the two published Anvil development keys.
tr '\n' '\0' < /tmp/veritas-publish-set.txt | xargs -0 grep -n -E \
  'BEGIN .*PRIVATE KEY|ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80|59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d' \
  || true

# Common token and credential assignments.
tr '\n' '\0' < /tmp/veritas-publish-set.txt | xargs -0 grep -n -i -E \
  'AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|xox[bp]-|sk-[A-Za-z0-9]{20,}|api[_-]?key *[:=]|passw(or)?d *[:=]|secret *[:=]' \
  | grep -v package-lock || true

# Sensitive files must not be in the publish set. Expect no output.
grep -E '\.(pem|db|sqlite|p12|pfx)$|(^|/)\.env($|\.local)|state\.json$' /tmp/veritas-publish-set.txt || true

# Ignore rules must cover local secrets and state.
git check-ignore -v .env.local .local/keys/issuer.pem data/veritas.db .anvil/state.json
```

Allowed matches:

- `contracts/fixtures/anvil-public-dev.json` holds Anvil's two published development keys (accounts 0 and 1). They are public and documented by Foundry. Never use them on a network that holds value.
- Code and tests that mention a pattern without holding a key: `backend/veritas/evidence/keys.py`, `backend/tests/unit/test_evidence.py`, `backend/tests/e2e/test_live_anchor.py`, and this file.

Any other match is a stop. Do not publish employer data, customer rows, or a generated `issuer.pem`.

## 2. Optional dedicated scanner (not run in this repository's Phase 09)

Neither gitleaks nor trufflehog was installed when Phase 09 was prepared, so the commands below were **not executed**. Run one of them yourself if you want a second opinion:

```bash
brew install gitleaks
gitleaks detect --no-git --source . --redact      # scans the working tree, including untracked files
gitleaks detect --source . --redact               # scans history once a commit exists
```

`--no-git` also scans git-ignored files in the working tree, so `.env.local` and `.local/keys/` will show up. Those are expected locally and must stay out of the publish set. Review the output with that in mind.

## 3. After publishing

If a real key or customer record is ever committed, rotate the key first, then rewrite history. Deleting the file in a later commit does not remove it from history.
