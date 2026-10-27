package ng.police.cases;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.util.*;
@Service
public class CaseStore {
    public record NewCase(String reference, String title, String category) {}
    public record CaseRecord(String reference, String title, String category, String status, Instant createdAt) {}
    private final ObjectMapper mapper;
    private final Path storePath;
    private final Map<String, CaseRecord> cases = new LinkedHashMap<>();
    public CaseStore(ObjectMapper mapper, @Value("${npcip.store-path:./data/cases.json}") String path) {
        this.mapper = mapper; this.storePath = Path.of(path).toAbsolutePath().normalize(); load();
    }
    private synchronized void load() {
        if (!Files.exists(storePath)) return;
        try {
            List<CaseRecord> loaded = mapper.readValue(storePath.toFile(), new TypeReference<List<CaseRecord>>() {});
            for (CaseRecord item : loaded) cases.put(item.reference(), item);
        } catch (IOException ex) {
            throw new IllegalStateException("Unable to read local case store; refusing to start with partial data", ex);
        }
    }
    public synchronized List<CaseRecord> list() {
        return cases.values().stream().sorted(Comparator.comparing(CaseRecord::createdAt).reversed()).toList();
    }
    public synchronized CaseRecord get(String reference) {
        CaseRecord item = cases.get(reference);
        if (item == null) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Case not found");
        return item;
    }
    public synchronized CaseRecord create(NewCase input) {
        if (input.reference() == null || input.reference().isBlank() || input.reference().length() > 24 || input.title() == null || input.title().isBlank() || input.title().length() > 180 || input.category() == null || input.category().isBlank() || input.category().length() > 80)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid case fields");
        String ref = input.reference().trim();
        if (cases.containsKey(ref)) throw new ResponseStatusException(HttpStatus.CONFLICT, "Case reference already exists");
        CaseRecord record = new CaseRecord(ref, input.title().trim(), input.category().trim(), "OPEN", Instant.now());
        cases.put(record.reference(), record);
        try { persist(); } catch (RuntimeException ex) { cases.remove(record.reference()); throw ex; }
        return record;
    }
    private void persist() {
        try {
            Files.createDirectories(storePath.getParent());
            Path tmp = storePath.resolveSibling(storePath.getFileName() + ".tmp");
            mapper.writerWithDefaultPrettyPrinter().writeValue(tmp.toFile(), cases.values());
            try { Files.move(tmp, storePath, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE); }
            catch (IOException atomicNotSupported) { Files.move(tmp, storePath, StandardCopyOption.REPLACE_EXISTING); }
        } catch (IOException ex) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Local case store write failed", ex);
        }
    }
}
