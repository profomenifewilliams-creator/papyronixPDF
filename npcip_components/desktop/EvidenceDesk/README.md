# EvidenceDesk (C# / .NET 8)

Local-only utility for file hashing, digest verification and JSON manifest export. It does not acquire devices, bypass locks, access remote accounts or send files over a network.

```bash
dotnet run --project npcip_components/desktop/EvidenceDesk -- hash ./sample.txt
dotnet run --project npcip_components/desktop/EvidenceDesk -- verify ./sample.txt <64-character-sha256>
dotnet run --project npcip_components/desktop/EvidenceDesk -- manifest ./sample.txt ./sample-manifest.json
```

A matching digest means the bytes match the supplied SHA-256. It does not prove who created a file or whether collection was lawful.
