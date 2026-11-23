# Security

## Reporting a problem

If you find a security problem in this repository, or something that should not
be public (a password, API key, token or other credential, personal data, or
data we are not allowed to share), please **do not open a public issue**.
Tell us privately through the [Trase contact page](https://trase.earth/contact-us)
or at info@trase.earth instead.

## If you committed a secret by mistake

1. Revoke or rotate the credential straight away. Deleting it in a new commit is
   not enough: it stays in the git history and in any forks or clones.
2. Let the maintainers know, so they can decide whether to rewrite the history.

## Preventing leaks

This repository runs [gitleaks](https://github.com/gitleaks/gitleaks) and other
checks through [pre-commit](https://pre-commit.com), both locally and in CI.
Set it up once after cloning:

```bash
pip install pre-commit
pre-commit install
```
