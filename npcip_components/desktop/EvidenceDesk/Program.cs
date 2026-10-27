using System.Security.Cryptography;
using System.Text.Json;
static async Task<(FileInfo Info, string Hash)> FingerprintAsync(string path) {
    var full = Path.GetFullPath(path);
    if (!File.Exists(full)) throw new FileNotFoundException("File was not found", full);
    await using var stream = new FileStream(full, FileMode.Open, FileAccess.Read, FileShare.Read, 1024 * 1024, useAsync: true);
    var hash = await SHA256.HashDataAsync(stream);
    return (new FileInfo(full), Convert.ToHexString(hash).ToLowerInvariant());
}
if (args.Length < 2 || args[0] is not ("hash" or "verify" or "manifest")) {
    Console.Error.WriteLine("NPCIP EvidenceDesk — local-only file integrity utility\nUsage:\n  EvidenceDesk hash <file>\n  EvidenceDesk verify <file> <expected-sha256>\n  EvidenceDesk manifest <file> [output.json]");
    return 2;
}
try {
    var (info, hash) = await FingerprintAsync(args[1]);
    Console.WriteLine($"file={info.Name}\nsize_bytes={info.Length}\nsha256={hash}");
    if (args[0] == "verify") {
        if (args.Length != 3 || args[2].Length != 64 || args[2].Any(c => !Uri.IsHexDigit(c))) { Console.Error.WriteLine("Expected SHA-256 must be exactly 64 hexadecimal characters."); return 2; }
        var match = CryptographicOperations.FixedTimeEquals(Convert.FromHexString(hash), Convert.FromHexString(args[2]));
        Console.WriteLine(match ? "verification=PASS" : "verification=FAIL");
        return match ? 0 : 1;
    }
    if (args[0] == "manifest") {
        var manifest = new { schema = "npcip.evidence-manifest.v1", fileName = info.Name, sizeBytes = info.Length, sha256 = hash, computedAtUtc = DateTimeOffset.UtcNow, computation = "local SHA-256", limitation = "Fingerprint only; not proof of origin, authenticity, lawful collection, or complete chain of custody." };
        var json = JsonSerializer.Serialize(manifest, new JsonSerializerOptions { WriteIndented = true });
        if (args.Length >= 3) { await File.WriteAllTextAsync(Path.GetFullPath(args[2]), json); Console.WriteLine($"manifest_written={Path.GetFullPath(args[2])}"); }
        else Console.WriteLine(json);
    }
    Console.WriteLine("notice=local-only; file was read but not changed or uploaded"); return 0;
} catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or FormatException) {
    Console.Error.WriteLine($"error={ex.Message}"); return 1;
}
