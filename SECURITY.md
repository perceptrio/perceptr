# Security Policy

## Supported Versions

Security fixes are applied to the latest release on the default branch.

## Reporting a Vulnerability

If you discover a security issue, please **do not** open a public GitHub issue.

Email **asoliman@perceptr.io** with:

- A description of the vulnerability
- Steps to reproduce
- Impact assessment

We will acknowledge receipt within 48 hours and work on a fix as quickly as possible.

## Secrets

- Never commit `.env` files or API keys
- Rotate keys if they are accidentally exposed
- Use strong random values for `SECRET_KEY` and `REFRESH_SECRET_KEY` in production
