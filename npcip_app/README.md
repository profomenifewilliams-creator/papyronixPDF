# NPCIP deployment workspace

This is a public-hosting demo for the Nigeria Police Cyber Intelligence Platform concept. It is not an official or approved Nigeria Police Force system.

- Django web portal: demo accounts, user-scoped case management, evidence upload with SHA-256 fingerprint and download-time integrity check, audit events and admin-only CSV export.
- Runs using Django, SQLite by default, and local file storage.
- No third-party investigation APIs are called by the application.

## Important limitations

This deployment workspace is intended only for synthetic training data. Render free service files and the SQLite database may be lost on redeploy, restart, or instance replacement. Do not upload authentic case records or evidence. Before any operational use, migrate to a controlled institution-owned environment with PostgreSQL, durable encrypted evidence storage, immutable audit logs, role-based approvals, security testing, backup and restore drills, and formal legal/privacy review.

The C, C++, C# and Java/Spring Boot source components remain in the downloadable source bundle; this Render service deploys the Django web workspace only.
