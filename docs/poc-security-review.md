# Proof-of-concept security review

Review date: 7 September 2026

## Scope and conclusion

This is a focused review for obvious and reasonably foreseeable data-exposure
mistakes in the standalone hosted proof of concept. It is not a penetration test
or a certification for production use.

The public Career Pathways Explorer intentionally exposes its read model. The PD
administration screens and APIs require HTTP Basic credentials and are read-only.
Within that scope, no obvious unauthenticated route to the administration data or
write operation was found.

## Controls verified in code

- Administration routes challenge unauthenticated requests and use constant-time
  credential comparison.
- The hosted administration profile blocks non-GET requests.
- Hosted PostgreSQL sessions default every transaction to read-only.
- Supabase tables have row-level security enabled and no anonymous policies.
- API documentation and the OpenAPI document are disabled.
- Responses use anti-framing, content-sniffing, referrer, permissions, CSP, HSTS,
  and no-store cache headers; protected responses vary on Authorization.
- Application exceptions redact database and administration passwords and request
  bodies are not logged.
- The container runs as a non-root user and excludes local databases, generated
  data, logs, backups, environment files, tests, and source snapshots.
- The cloud image uses a reduced dependency set and does not install the local
  sentence-transformer stack. Model-backed semantic search is disabled in this
  hosted PoC.

## Accepted limitations for this PoC

- HTTP Basic authentication is a shared, single-factor gate. It is acceptable only
  for temporary, tightly controlled review—not for enterprise rollout.
- Railway currently connects with the Supabase project database owner credential.
  Read-only transactions are enforced by the application, but a dedicated
  least-privilege database role would provide stronger isolation.
- The Career Pathways Explorer is public by design. Automated traffic could create
  Railway or Supabase usage even though it cannot reach protected administration
  routes.
- Security still depends on account controls in GitHub, Railway, and Supabase.

## Operator checks

- Rotate the Supabase database password once after setup. It was displayed in a
  terminal screenshot during this build; update both the Railway database URL and
  `PGPASSWORD` together after rotation. The password itself is not in Git.
- Enable MFA on GitHub, Railway, and Supabase accounts.
- Keep Railway secrets only in its Variables store; never place credentials in the
  repository, screenshots, tickets, or logs. Rotate any credential that is exposed.
- Enable GitHub secret scanning and dependency alerts for the private repository.
- Set Railway usage alerts or a hard spending limit and retain serverless sleep.
- Review Supabase backups and recovery settings appropriate to the PoC's value.

## Required before real sensitive data or broader use

- Replace shared Basic authentication with organisational identity (for example,
  Microsoft Entra ID), role-based access, session controls, and audit logging.
- Give the application a dedicated database role with SELECT only on required
  tables, and test the permissions independently of the application.
- Reintroduce write functions only with authorisation, CSRF protection, validation,
  audit trails, and recovery controls.
- Complete formal threat modelling, dependency scanning, and penetration testing.
