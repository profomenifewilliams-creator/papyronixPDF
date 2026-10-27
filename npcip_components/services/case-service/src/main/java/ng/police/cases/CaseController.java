package ng.police.cases;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.*;
import java.util.List;
@RestController
@RequestMapping("/internal/cases")
public class CaseController {
    public record NewCase(@NotBlank String reference, @NotBlank String title, @NotBlank String category) {}
    private final CaseStore store;
    public CaseController(CaseStore store) { this.store = store; }
    @GetMapping public List<CaseStore.CaseRecord> list() { return store.list(); }
    @PostMapping public CaseStore.CaseRecord create(@Valid @RequestBody NewCase input) {
        return store.create(new CaseStore.NewCase(input.reference(), input.title(), input.category()));
    }
    @GetMapping("/{reference}") public CaseStore.CaseRecord get(@PathVariable String reference) { return store.get(reference); }
}
