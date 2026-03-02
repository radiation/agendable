# Security Policy

## Supported Versions

This project is actively developed on the `main` branch.

Security updates are applied to the latest version only unless otherwise noted.

| Version | Supported |
|---------|-----------|
| main    | ✅ |
| older releases | ❌ |

---

## Reporting a Vulnerability

If you believe you have found a security vulnerability, **please do not open a public issue**.

Instead, report it privately using one of the following methods:

### Preferred: GitHub Security Advisories
1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Submit the details privately.

This allows coordinated disclosure and prevents accidental exposure.

### Alternative
If GitHub advisories are unavailable, you may open a private discussion or contact the maintainer directly.

---

## What to Include

Please include as much detail as possible:

- Description of the vulnerability
- Steps to reproduce
- Proof of concept (if available)
- Potential impact
- Suggested remediation (optional)

---

## Response Expectations

Because this is a personal project, response times may vary, but the general targets are:

- Initial acknowledgement: within **3–5 days**
- Status update: within **7–14 days**
- Fix timeline: depends on severity and complexity

---

## Disclosure Policy

- Vulnerabilities will be fixed before public disclosure whenever possible.
- Credit will be given to reporters unless anonymity is requested.
- Coordinated disclosure is encouraged.

---

## Security Fix Workflow

- This repository uses a PR-only workflow for `main`; fixes are merged via pull request (no direct pushes).
- For sensitive vulnerabilities, maintainers may use private advisory collaboration first, then merge a minimal fix PR to `main`.
- Public issue/PR discussions should avoid exploit details until a fix is released.

---

## Scope

This policy applies only to vulnerabilities in this repository's source code and released artifacts.

Issues related to third-party dependencies should also be reported upstream when appropriate.

---

## Security Best Practices

Users are encouraged to:

- Keep dependencies up to date
- Avoid committing secrets or credentials
- Use least-privilege credentials when deploying

---

Thank you for helping improve the security of this project.