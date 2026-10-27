# NPCIP Multi-language components

This directory contains standalone code modules for the NPCIP development MVP. The running Render app is the Django web service under \`npcip_app/\`; these independent components must be compiled/deployed as separate runtimes. No third-party investigative APIs are used.

## Languages and responsibilities
- C: streaming file SHA-256 and basic signature hints.
- C++: equivalent file fingerprinting plus JSONL audit action counts.
- C# / .NET 8: hash, verify, and export a JSON fingerprint manifest.
- Java 21 / Spring Boot: token-protected internal case registry with local JSON persistence.
- HTML / CSS / JavaScript: the Django pages and responsive UI.
- Python / Django: account login, case workflows, evidence register, SHA-256 checks and audit trail.

## C / C++ build and smoke test
Compile with the shared header:
\`\`\`bash
cc -std=c11 -Wall -Wextra -Werror -Inpcip_components/native/shared npcip_components/native/c/filehash.c -o npc-filehash
g++ -std=c++17 -Wall -Wextra -Werror -Inpcip_components/native/shared npcip_components/native/cpp/filehash.cpp -o npc-filehash-cpp
g++ -std=c++17 -Wall -Wextra -Werror npcip_components/native/cpp/audit_analyzer.cpp -o npc-audit-analyzer
\`\`\`
The C/C++ tools are offline-only and do not upload or alter input files.

## Spring Boot service
The API uses a token we define and own, not a third-party API. Internal endpoints require the \`X-NPCIP-Service-Token\` header; when no \`NPCIP_SERVICE_TOKEN\` is configured, access fails closed. Keep this service on private networking or behind strict access controls. \`/actuator/health\` returns a health status without detailed diagnostics.

Use fake/demo data only. JSON-file persistence is a prototype, not a database or evidentiary archive. For a real pilot, use a reviewed database, durable encrypted storage, immutable audit logging, formal authentication/authorization, backup/restore and legal/privacy review.
